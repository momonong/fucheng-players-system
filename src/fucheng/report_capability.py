"""Short-lived report-only credentials derived from the server's private key."""
import base64
import hashlib
import hmac
import json
import re
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict

from .models import Admin, now_utc

TTL_SECONDS = 3600
DOMAIN = b'fucheng-report-capability-v1\0'
KEYS = {'aud','version','device_id','report_id','iat','exp','admin_id','admin_version'}


class CapabilityRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    report_id: UUID


def issue_token(settings, admin, report_id, timestamp):
    claims = dict(aud='deployment-report-upload',version=1,device_id=settings.report_upload_device_id,
        report_id=str(report_id),iat=timestamp,exp=timestamp+TTL_SECONDS,admin_id=admin.id,admin_version=admin.version)
    encoded = base64.urlsafe_b64encode(json.dumps(claims,sort_keys=True,separators=(',',':')).encode()).decode().rstrip('=')
    signature = hmac.new(settings.report_upload_token.encode('ascii'),DOMAIN+encoded.encode('ascii'),hashlib.sha256).hexdigest()
    return 'fcr1.'+encoded+'.'+signature


def require_report_token(settings, supplied, report_id, db):
    def invalid():
        raise HTTPException(401,'報告回傳憑證無效或已到期；保留原 report_id 重新取得憑證')
    # Preserve pre-existing fixed device credentials for installed senders.
    expected=hashlib.sha256(settings.report_upload_token.encode('ascii')).digest()
    actual=hashlib.sha256(supplied.encode('utf-8')).digest()
    if hmac.compare_digest(expected,actual):
        return
    if len(supplied)>1024 or not re.fullmatch(r'fcr1\.[A-Za-z0-9_-]+\.[0-9a-f]{64}',supplied):
        invalid()
    _,encoded,signature=supplied.split('.')
    wanted=hmac.new(settings.report_upload_token.encode('ascii'),DOMAIN+encoded.encode('ascii'),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(wanted,signature):
        invalid()
    try:
        raw=base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4))
        claims=json.loads(raw)
        if not isinstance(claims,dict) or set(claims)!=KEYS:
            invalid()
        # Require a unique, canonical JSON representation: no duplicate keys or coercion.
        if json.dumps(claims,sort_keys=True,separators=(',',':')).encode()!=raw:
            invalid()
        if any(type(claims[k]) is not int for k in ('version','iat','exp','admin_version')):
            invalid()
        if any(type(claims[k]) is not str for k in ('aud','device_id','report_id','admin_id')):
            invalid()
        now=int(now_utc().timestamp())
        if (claims['aud']!='deployment-report-upload' or claims['version']!=1
            or claims['device_id']!=settings.report_upload_device_id or claims['report_id']!=str(report_id)
            or str(UUID(claims['report_id']))!=claims['report_id']
            or str(UUID(claims['admin_id']))!=claims['admin_id']
            or not (0 < claims['exp']-claims['iat'] <= TTL_SECONDS)
            or claims['iat']>now or claims['exp']<=now):
            invalid()
        admin=db.get(Admin,claims['admin_id'],populate_existing=True)
        if not admin or not admin.is_active or admin.must_change_password or admin.version!=claims['admin_version']:
            invalid()
    except (ValueError,TypeError,KeyError,UnicodeError):
        invalid()
