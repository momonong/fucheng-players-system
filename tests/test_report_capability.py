"""Reject capability escalation, rebinding, expiry and revoked administrators."""
import base64
from datetime import timedelta
import hashlib
import hmac
import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from fucheng.models import Admin, AdminAudit, LoginSession, now_utc
from test_device_reports import TOKEN, device, send
from test_deployment_report import report


def issue(client, password, key, prefix=''):
    login = client.post(prefix+'/api/auth/login',json={'username':'admin','password':password})
    assert login.status_code == 200
    return client.post(prefix+'/api/admin/deployment-report-capability',json={'report_id':key},
        headers={'X-CSRF-Token':login.json()['csrf_token']})


@pytest.mark.parametrize('prefix',['','/fucheng'])
def test_capability_session_csrf_one_report_scope_and_secret_free_audit(app, admin_password, prefix):
    key = str(uuid4())
    with device(app,base_path=prefix) as c:
        assert c.post(prefix+'/api/admin/deployment-report-capability',json={'report_id':key}).status_code==401
        login=c.post(prefix+'/api/auth/login',json={'username':'admin','password':admin_password}).json()
        assert c.post(prefix+'/api/admin/deployment-report-capability',json={'report_id':key}).status_code==403
        response=c.post(prefix+'/api/admin/deployment-report-capability',json={'report_id':key},headers={'X-CSRF-Token':login['csrf_token']})
        assert response.status_code==200, response.text
        audit_view=c.get(prefix+'/api/admin/admin-audits')
        assert audit_view.status_code==200
        assert audit_view.json()[0]['changes']['report_id']=={'before':None,'after':key}
        assert audit_view.json()[0]['source']=='web'
        value=response.json(); token=value['token']
        assert set(value)=={'token','device_id','report_id','expires_at'} and value['report_id']==key
        assert token.startswith('fcr1.') and TOKEN not in token and len(token)<1024
        c.post(prefix+'/api/auth/logout',headers={'X-CSRF-Token':login['csrf_token']})
        headers={'Content-Type':'application/json','X-Fucheng-Report-Token':token}
        payload=report()
        receipt=send(c,payload,key=key,prefix=prefix,headers=headers)
        assert receipt.status_code==200, receipt.text
        assert send(c,payload,key=key,prefix=prefix,headers=headers).json()==receipt.json()
        assert send(c,key=str(uuid4()),prefix=prefix,headers=headers).status_code==401
        assert send(c,key=key,prefix=prefix,headers=headers|{'X-Fucheng-Report-Token':token[:-1]+'!'}).status_code==401
        for path in ('/api/auth/me','/api/admin/members','/api/admin/deployment-reports'):
            assert c.get(prefix+path,headers=headers).status_code==401
        with app.state.session_factory() as db:
            audit=db.scalar(select(AdminAudit).where(AdminAudit.action=='report_capability'))
            assert audit and key in audit.changes_json
            assert token not in audit.changes_json and TOKEN not in audit.changes_json


@pytest.mark.parametrize('mutation',['expired','ttl','future','device','aud','version','boolean','extra','admin_version','disabled','must_change','stale_session'])
def test_rejects_invalid_signed_claims_and_account_revocation(app,admin_password,mutation):
    key=str(uuid4())
    with device(app) as c:
        response=issue(c,admin_password,key)
        assert response.status_code==200, response.text
        token=response.json()['token']
        _,encoded,_=token.split('.')
        claims=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
        if mutation=='stale_session':
            with app.state.session_factory.begin() as db:
                for row in db.scalars(select(LoginSession)): row.created_at=now_utc()-timedelta(minutes=6)
            assert c.post('/api/admin/deployment-report-capability',json={'report_id':key},headers={'X-CSRF-Token':c.get('/api/auth/me').json()['csrf_token']}).status_code==403
            return
        if mutation in ('disabled','must_change','admin_version'):
            with app.state.session_factory.begin() as db:
                admin=db.scalar(select(Admin))
                if mutation=='disabled': admin.is_active=False
                elif mutation=='must_change': admin.must_change_password=True
                else: admin.version+=1
        else:
            if mutation=='expired': claims['iat']-=7200;claims['exp']-=7200
            elif mutation=='ttl':claims['exp']=claims['iat']+3601
            elif mutation=='future':claims['iat']+=120;claims['exp']+=120
            elif mutation=='device':claims['device_id']='another-device'
            elif mutation=='aud':claims['aud']='admin'
            elif mutation=='version':claims['version']=2
            elif mutation=='boolean':claims['version']=True
            elif mutation=='extra':claims['extra']='unexpected'
            encoded=base64.urlsafe_b64encode(json.dumps(claims,sort_keys=True,separators=(',',':')).encode()).decode().rstrip('=')
            signature=hmac.new(TOKEN.encode(),b'fucheng-report-capability-v1\0'+encoded.encode(),hashlib.sha256).hexdigest()
            token='fcr1.'+encoded+'.'+signature
        assert send(c,key=key,headers={'Content-Type':'application/json','X-Fucheng-Report-Token':token}).status_code==401
