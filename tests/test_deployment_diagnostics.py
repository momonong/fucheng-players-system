"""Container diagnostics preserve keys, reports, credentials and Windows boundaries."""
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from fucheng.app import create_app
from fucheng.models import DeploymentReportAudit
from test_deployment_report import report as windows_report, upload


def payload(version=0, key=None, probe=False):
    return {'version': version, 'request_id': key or str(uuid4()), 'probe_network': probe}


def run(client, auth, body=None):
    return client.post('/api/admin/deployment-report/run', headers=auth, json=body or payload())


def test_run_permissions_container_boundaries_and_downloads(app, client, auth):
    with TestClient(app) as visitor:
        assert run(visitor, {}).status_code == 401
    assert run(client, {}).status_code == 403
    body = payload()
    response = run(client, auth, body)
    assert response.status_code == 200, response.text
    saved = response.json()
    report = saved['report']
    assert report['schema_version'] == 2 and report['report_type'] == 'container_runtime'
    assert 'host' not in report and report['runtime']['system']
    for check in report['checks']:
        if check['id'] in {'windows_edition', 'cold_boot_recovery', 'docker_engine', 'public_ingress', 'backup_write_and_restore'}:
            assert check['status'] == 'NOT_TESTED'
    assert saved['run']['request_id'] == body['request_id']
    assert saved['run']['send_state'] == 'not_configured'
    assert client.get('/api/admin/deployment-report').json() == saved
    assert client.get('/api/admin/deployment-report/markdown').text.startswith('# App／Linux 容器部署檢查報告')
    assert client.get('/api/admin/deployment-report/json').json() == report
    assert client.get('/api/admin/deployment-report/runs/'+body['request_id']).json() == saved
    assert 'password' not in json.dumps(report).lower()
    assert str(app.state.settings.static_dir) not in json.dumps(saved)


def test_same_key_is_immutable_actor_payload_and_version_bound(app, client, auth, monkeypatch):
    body = payload()
    first = run(client, auth, body)
    assert first.status_code == 200, first.text
    import fucheng.deployment_diagnostics as diagnostics
    monkeypatch.setattr(diagnostics, 'collect_report', lambda *args: pytest.fail('must not recollect'))
    assert run(client, auth, body).json() == first.json()
    assert run(client, auth, {**body, 'probe_network': True}).status_code == 409
    assert run(client, auth, {**body, 'version': 1}).status_code == 409
    assert run(client, auth, payload()).status_code == 409
    with app.state.session_factory() as db:
        assert len(db.scalars(select(DeploymentReportAudit)).all()) == 1
    from fucheng.models import Admin
    from fucheng.security import hash_password
    with app.state.session_factory.begin() as db:
        db.add(Admin(username='peer', password_hash=hash_password('Synthetic-peer-long-password!')))
    with TestClient(app) as peer:
        login = peer.post('/api/auth/login', json={'username':'peer','password':'Synthetic-peer-long-password!'})
        csrf = {'X-CSRF-Token':login.json()['csrf_token']}
        assert peer.get('/api/admin/deployment-report/runs/'+body['request_id']).status_code == 200
        assert run(peer, csrf, body).status_code == 409
        assert peer.post('/api/admin/deployment-report/runs/'+body['request_id']+'/send', headers=csrf).status_code == 403


def test_manual_schema1_replaces_current_but_preserves_run(client, auth):
    body = payload()
    assert run(client, auth, body).status_code == 200
    assert upload(client, windows_report(), headers=auth, version=1).json()['run'] is None
    assert client.get('/api/admin/deployment-report/runs/'+body['request_id']).json()['report']['schema_version'] == 2


def test_send_lost_response_restart_and_receipt_validation(app, client, auth, tmp_path, monkeypatch):
    import fucheng.deployment_diagnostics as diagnostics
    from fucheng.models import DeploymentDiagnosticRun
    token = tmp_path/'private-secret'
    token.write_text('ab'*32)
    configured = replace(app.state.settings, report_send_enabled=True, report_send_device_id='synthetic-device', report_send_token_file=token)
    application = create_app(configured)
    attempts = []
    def lost(report_id, device_id, raw, secret):
        with application.state.session_factory() as db:
            assert db.get(DeploymentDiagnosticRun, report_id).send_state == 'unknown'
        attempts.append((report_id, raw))
        raise TimeoutError()
    monkeypatch.setattr(diagnostics, 'deliver_report', lost)
    body = payload()
    with TestClient(application) as other:
        other.cookies.update(client.cookies)
        first = run(other, auth, body)
        assert first.status_code == 200, first.text
        assert first.json()['run']['send_state'] == 'unknown'
        assert run(other, auth, body).json()['run']['send_state'] == 'unknown'
        assert len(attempts) == 1
    application.state.engine.dispose()
    reopened = create_app(configured)
    def received(report_id, device_id, raw, secret):
        assert (report_id,raw) == attempts[0]
        import hashlib
        return {'report_id':report_id, 'device_id':device_id, 'digest':hashlib.sha256(raw).hexdigest(), 'received_at':__import__('fucheng.models',fromlist=['now_utc']).now_utc().isoformat()}
    monkeypatch.setattr(diagnostics, 'deliver_report', received)
    with TestClient(reopened) as other:
        other.cookies.update(client.cookies)
        saved = other.get('/api/admin/deployment-report').json()
        assert saved['run']['send_state'] == 'unknown'
        sent = other.post('/api/admin/deployment-report/runs/'+body['request_id']+'/send', headers=auth)
        assert sent.status_code == 200, sent.text
        assert sent.json()['run']['send_state'] == 'received'
        monkeypatch.setattr(diagnostics, 'deliver_report', lambda *args: pytest.fail('must not resend receipt'))
        assert other.post('/api/admin/deployment-report/runs/'+body['request_id']+'/send', headers=auth).json() == sent.json()
        assert 'ab'*32 not in json.dumps(sent.json())
    reopened.state.engine.dispose()


def test_capacity_no_replacement_and_new_run_after_current_version(client, auth, monkeypatch):
    import fucheng.deployment_diagnostics as diagnostics
    assert run(client, auth).status_code == 200
    monkeypatch.setattr(diagnostics, 'MAX_RUNS', 1)
    assert run(client, auth, payload(version=1)).status_code == 507
    assert client.get('/api/admin/deployment-report').json()['version'] == 1


def test_schema2_parser_strict_and_receiver(app, client, auth):
    from fucheng.deployment_report import parse_report
    from fucheng.config import Settings
    saved = run(client, auth).json()['report']
    assert parse_report(json.dumps(saved).encode()).schema_version == 2
    bad = {**saved, 'host': windows_report()['host']}
    with pytest.raises(Exception):
        parse_report(json.dumps(bad).encode())
    altered = json.loads(json.dumps(saved))
    next(c for c in altered['checks'] if c['id']=='windows_edition')['status']='PASS'
    with pytest.raises(Exception):
        parse_report(json.dumps(altered).encode())
    settings = replace(app.state.settings, report_upload_enabled=True, report_upload_device_id='synthetic-device', report_upload_token='ab'*32)
    receiver = create_app(settings)
    with TestClient(receiver) as other:
        other.cookies.update(client.cookies)
        key = str(uuid4())
        response = other.post('/api/deployment-reports/'+key, json=saved, headers={'X-Fucheng-Report-Token':'ab'*32})
        assert response.status_code == 200, response.text
        assert other.get('/api/admin/deployment-reports').json()['items'][0]['claimed_host_name'] == saved['runtime']['name']
        assert other.get('/api/admin/deployment-reports/'+key+'/markdown').text.startswith('# App／Linux')
    receiver.state.engine.dispose()


def test_unconfigured_saved_run_can_bind_first_sender_once(app, client, auth, tmp_path, monkeypatch):
    body = payload()
    assert run(client, auth, body).json()['run']['send_state'] == 'not_configured'
    secret = tmp_path/'first-credential'
    secret.write_text('cd'*32)
    import fucheng.deployment_diagnostics as diagnostics
    import hashlib
    from fucheng.models import now_utc
    def deliver(key, device, raw, token):
        return {'report_id':key,'device_id':device,'digest':hashlib.sha256(raw).hexdigest(),'received_at':now_utc().isoformat()}
    monkeypatch.setattr(diagnostics,'deliver_report',deliver)
    configured = create_app(replace(app.state.settings, report_send_enabled=True, report_send_device_id='first-device', report_send_token_file=secret))
    with TestClient(configured) as other:
        other.cookies.update(client.cookies)
        sent = other.post('/api/admin/deployment-report/runs/'+body['request_id']+'/send', headers=auth)
        assert sent.json()['run']['send_state'] == 'received', sent.text
        assert sent.json()['run']['device_id'] == 'first-device'
    configured.state.engine.dispose()


@pytest.mark.parametrize('kind', ['device','id','digest','time','redirect'])
def test_invalid_receipts_never_claim_received(app, client, auth, tmp_path, monkeypatch, kind):
    import fucheng.deployment_diagnostics as diagnostics
    from fucheng.models import now_utc
    import hashlib
    secret=tmp_path/'secret'
    secret.write_text('ef'*32)
    def invalid(key, device, raw, token):
        receipt={'report_id':key,'device_id':device,'digest':hashlib.sha256(raw).hexdigest(),'received_at':now_utc().isoformat()}
        if kind=='redirect':
            raise diagnostics.DeliveryRejected(302)
        field={'device':'device_id','id':'report_id','digest':'digest','time':'received_at'}[kind]
        receipt[field]='invalid'
        return receipt
    monkeypatch.setattr(diagnostics,'deliver_report',invalid)
    configured=create_app(replace(app.state.settings,report_send_enabled=True,report_send_device_id='synthetic-device',report_send_token_file=secret))
    with TestClient(configured) as other:
        other.cookies.update(client.cookies)
        result=run(other,auth)
        assert result.status_code==200, result.text
        assert result.json()['run']['send_state'] != 'received'
        assert result.json()['run']['receipt'] is None
    configured.state.engine.dispose()


def test_transport_total_deadline_and_secret_not_in_command(monkeypatch):
    import subprocess
    from fucheng import report_delivery
    def expired(args, **kwargs):
        assert args[0] == __import__('sys').executable
        assert kwargs['timeout'] <= 15 and kwargs['shell'] is False
        assert 'ab'*32 not in repr(args) and 'env' not in kwargs
        assert b'abab' in kwargs['input']
        raise subprocess.TimeoutExpired(args, kwargs['timeout'])
    monkeypatch.setattr(subprocess,'run',expired)
    with pytest.raises(TimeoutError):
        report_delivery.deliver_report(str(uuid4()),'synthetic-device',b'{}','ab'*32)


def test_0015_only_adds_run_table_preserves_rows_and_freezes_report(tmp_path, monkeypatch):
    import sqlite3
    from alembic import command
    from alembic.config import Config
    path=tmp_path/'migration.db'
    monkeypatch.setenv('FUCHENG_DATABASE_URL',f'sqlite:///{path}')
    config=Config('alembic.ini')
    command.upgrade(config,'0014_doubles_registration')
    with sqlite3.connect(path) as db:
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='alembic_version'")]
        before={table:(list(db.execute('SELECT * FROM '+table)), list(db.execute('PRAGMA table_info('+table+')'))) for table in tables}
    command.upgrade(config,'head')
    command.check(config)
    with sqlite3.connect(path) as db:
        after={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='alembic_version'")}
        assert after==set(tables)|{'deployment_diagnostic_runs'}
        for table,values in before.items():
            assert (list(db.execute('SELECT * FROM '+table)),list(db.execute('PRAGMA table_info('+table+')')))==values
        db.execute("INSERT INTO admins (id,username,password_hash,is_active,created_at,updated_at,version,must_change_password) VALUES ('a','synthetic','synthetic',1,'2026-01-01','2026-01-01',1,0)")
        db.execute("INSERT INTO deployment_diagnostic_runs VALUES ('r','a',?,1,'{}',?,2,?,NULL,'not_configured','saved',NULL,'2026-01-01','2026-01-01')",('0'*64,'0'*64,'https://momonong.me/fucheng/api/deployment-reports'))
        for statement in ("UPDATE deployment_diagnostic_runs SET report_json='changed'", "DELETE FROM deployment_diagnostic_runs"):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(statement)
        db.execute("UPDATE deployment_diagnostic_runs SET device_id='original',send_state='unknown'")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE deployment_diagnostic_runs SET device_id='replacement'")


def test_collector_version_conflict_does_not_replace_concurrent_manual_report(client, auth, monkeypatch):
    import fucheng.deployment_diagnostics as diagnostics
    original=diagnostics.collect_report
    def concurrent(settings, db, network):
        result=original(settings,db,network)
        assert upload(client,windows_report(),headers=auth).status_code==200
        return result
    monkeypatch.setattr(diagnostics,'collect_report',concurrent)
    assert run(client,auth).status_code==409
    assert client.get('/api/admin/deployment-report').json()['report']['schema_version']==1


def test_capacity_bytes_and_missing_invalid_secret_keep_local(client, auth, app, tmp_path, monkeypatch):
    import fucheng.deployment_diagnostics as diagnostics
    monkeypatch.setattr(diagnostics,'MAX_RUN_BYTES',1)
    assert run(client,auth).status_code==507
    assert client.get('/api/admin/deployment-report').json()['version']==0
    monkeypatch.setattr(diagnostics,'MAX_RUN_BYTES',64*1024*1024)
    invalid=tmp_path/'invalid'
    invalid.write_text('not-a-token')
    settings=replace(app.state.settings,report_send_enabled=True,report_send_device_id='synthetic',report_send_token_file=invalid)
    configured=create_app(settings)
    with TestClient(configured) as other:
        other.cookies.update(client.cookies)
        assert run(other,auth).json()['run']['send_state']=='not_configured'
    configured.state.engine.dispose()


@pytest.mark.parametrize('reference',['./assets/app.js','/assets/app.js','/fucheng/assets/app.js'])
def test_existing_vite_relative_and_prefixed_static_assets(app, tmp_path, reference):
    from fucheng.deployment_diagnostics import collect_report
    static=tmp_path/'static';(static/'assets').mkdir(parents=True)
    (static/'assets/app.js').write_text('synthetic bundled asset')
    (static/'index.html').write_text('<html><script type="module" src="'+reference+'"></script></html>')
    with app.state.session_factory() as db:
        result=collect_report(replace(app.state.settings,static_dir=static,base_path='/fucheng'),db,False)
    assert next(c.status for c in result.checks if c.id=='static_assets')=='PASS'


@pytest.mark.parametrize('kind',['fifo','symlink','oversize','missing'])
def test_sender_rejects_nonregular_symlink_large_or_missing_private_files(app,tmp_path,kind):
    import os
    from fucheng.deployment_diagnostics import sender_credentials
    secret=tmp_path/'private-path-must-not-appear'
    if kind=='fifo': os.mkfifo(secret)
    elif kind=='symlink':
        target=tmp_path/'target';target.write_text('ab'*32);secret.symlink_to(target)
    elif kind=='oversize': secret.write_text('a'*257)
    settings=replace(app.state.settings,report_send_enabled=True,report_send_device_id='synthetic',report_send_token_file=secret)
    assert sender_credentials(settings) is None
    assert str(secret) not in repr(settings)


@pytest.mark.parametrize('reference',['./assets//outside.js','./assets/%2Foutside.js','./assets/../outside.js','./assets/%2e%2e/outside.js','./assets/escape.js'])
def test_static_assets_reject_absolute_traversal_and_symlink_escape(app,tmp_path,reference):
    from fucheng.deployment_diagnostics import collect_report
    static=tmp_path/'static';(static/'assets').mkdir(parents=True)
    outside=tmp_path/'outside.js';outside.write_text('must never read')
    (static/'outside.js').write_text('synthetic outside asset directory')
    (static/'assets/escape.js').symlink_to(outside)
    if reference=='./assets//outside.js': reference='./assets/'+str(outside)
    if reference=='./assets/%2Foutside.js': reference='./assets/'+str(outside).replace('/','%2F')
    (static/'index.html').write_text('<script src="'+reference+'"></script>')
    with app.state.session_factory() as db:
        result=collect_report(replace(app.state.settings,static_dir=static),db,False)
    assert next(c.status for c in result.checks if c.id=='static_assets')=='FAIL'


@pytest.mark.parametrize('regions,expected',[({'region1':True,'region2':True},'PASS'),({'region1':True,'region2':False},'WARN'),({'region1':False,'region2':False},'WARN')])
def test_container_tcp7844_checks_current_path_without_attesting_udp(app,monkeypatch,regions,expected):
    import fucheng.deployment_diagnostics as diagnostics
    monkeypatch.setattr(diagnostics,'probe_network',lambda:{'cloudflare_https':True,'registry_https':True,'cloudflare_tcp_7844':all(regions.values()),'cloudflare_tcp_regions':regions})
    with app.state.session_factory() as db:
        report=diagnostics.collect_report(app.state.settings,db,True)
    checks={check.id:check for check in report.checks}
    assert checks['cloudflare_tcp_7844'].status==expected
    assert '目前 app 容器的連線路徑' in checks['cloudflare_tcp_7844'].reason
    assert checks['cloudflare_udp_7844'].status=='NOT_TESTED'
    assert checks['public_ingress'].status=='NOT_TESTED'


@pytest.mark.parametrize('value',[[],None,True,12,'synthetic'])
def test_nonobject_backup_status_does_not_prevent_saved_report(app,client,auth,tmp_path,value):
    status=tmp_path/'backup-status.json'
    status.write_text(json.dumps(value))
    configured=create_app(replace(app.state.settings,backup_status_file=status))
    with TestClient(configured) as other:
        other.cookies.update(client.cookies)
        response=run(other,auth)
        assert response.status_code==200, response.text
        saved=response.json()
        check=next(check for check in saved['report']['checks'] if check['id']=='backup_status')
        assert check['status']=='NOT_TESTED'
        assert saved['version']==1
        assert other.get('/api/admin/deployment-report').json()['run']['request_id']==saved['run']['request_id']
    configured.state.engine.dispose()


def test_database_structure_missing_required_column_is_fail_without_business_reads(app):
    from fucheng.deployment_diagnostics import collect_report
    with app.state.engine.begin() as connection:
        connection.exec_driver_sql('DROP INDEX ix_members_name')
        connection.exec_driver_sql('ALTER TABLE members DROP COLUMN name')
    with app.state.session_factory() as db:
        report=collect_report(app.state.settings,db,False)
    check=next(check for check in report.checks if check.id=='database_structure')
    assert check.status=='FAIL'
    assert '未查詢會員或報名內容' in check.evidence
