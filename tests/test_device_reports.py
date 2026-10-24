"""Device credentials only append bounded reports; admin reads remain separate."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets
import sqlite3
from uuid import uuid4
import zipfile

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from fucheng.app import create_app
from fucheng.config import Settings
from fucheng.deployment_report import parse_report
from fucheng.device_reports import canonical_report
from fucheng.models import DeviceDeploymentReport, now_utc
from fucheng.public_guard import IngressLimiter, PublicGuard
from test_deployment_report import report

TOKEN = secrets.token_hex(32)
HEADERS = {'Content-Type': 'application/json', 'X-Fucheng-Report-Token': TOKEN}


@contextmanager
def device(app, **changes):
    values = dict(report_upload_enabled=True, report_upload_device_id='club-synthetic-01', report_upload_token=TOKEN)
    application = create_app(replace(app.state.settings, **(values | changes)))
    try:
        with TestClient(application) as client:
            yield client
    finally:
        application.state.engine.dispose()


def send(client, payload=None, *, key=None, prefix='', headers=None):
    return client.post(f'{prefix}/api/deployment-reports/{key or uuid4()}',
                       content=json.dumps(payload or report()).encode(), headers=headers or HEADERS)


def count(app):
    with app.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(DeviceDeploymentReport))


@pytest.mark.parametrize('prefix', ['', '/fucheng'])
def test_fixture_report_receipt_unknown_retry_and_admin_download(app, admin_password, prefix):
    with device(app, base_path=prefix) as client:
        key = str(uuid4())
        payload = report()
        payload['checks'][0]['status'] = 'FAIL'
        payload['summary']['PASS'] -= 1
        payload['summary']['FAIL'] += 1
        payload['host']['name'] = '<img src=x onerror="alert(1)">'
        # Fixture transport: the first server commit succeeds but its response is
        # treated as lost by the sender. A retry must recover the same receipt.
        lost_response = send(client, payload, key=key, prefix=prefix)
        assert lost_response.status_code == 200, lost_response.text
        retry = send(client, payload, key=key, prefix=prefix)
        assert retry.json() == lost_response.json()
        expected = hashlib.sha256(canonical_report(parse_report(json.dumps(payload).encode())).encode()).hexdigest()
        assert retry.json()['digest'] == expected
        assert set(retry.json()) == {'report_id', 'device_id', 'digest', 'received_at'}
        assert retry.json()['device_id'] == 'club-synthetic-01'
        assert count(app) == 1
        for path in ('/api/admin/deployment-reports', f'/api/admin/deployment-reports/{key}/json',
                     f'/api/admin/deployment-reports/{key}/markdown', '/api/admin/members', '/api/auth/me'):
            assert client.get(prefix + path, headers=HEADERS).status_code == 401
        assert client.get(f'{prefix}/api/deployment-reports/{key}', headers=HEADERS).status_code == 404
        login = client.post(prefix + '/api/auth/login', json={'username':'admin', 'password':admin_password})
        assert login.status_code == 200
        listed = client.get(prefix + '/api/admin/deployment-reports')
        assert listed.status_code == 200 and listed.json()['next_before'] is None
        assert listed.json()['items'][0]['summary']['FAIL'] == 1
        assert listed.json()['items'][0]['claimed_host_name'] == payload['host']['name']
        for format in ('json', 'markdown'):
            response = client.get(f'{prefix}/api/admin/deployment-reports/{key}/{format}')
            assert response.status_code == 200
            assert response.headers['Cache-Control'] == 'no-store'
            assert response.headers['X-Content-Type-Options'] == 'nosniff'
            assert response.headers['X-Fucheng-Report-Digest'] == expected
            assert 'attachment;' in response.headers['Content-Disposition']
        assert '<img' not in client.get(f'{prefix}/api/admin/deployment-reports/{key}/markdown').text
        assert client.get(prefix + '/api/admin/deployment-report').json()['version'] == 0
        changed = dict(payload, host=dict(payload['host'], name='changed'))
        assert send(client, changed, key=key, prefix=prefix).status_code == 409
        # Admin session and CSRF do not replace the device credential.
        assert send(client, payload, key=str(uuid4()), prefix=prefix,
                    headers={'Content-Type':'application/json', 'X-CSRF-Token':login.json()['csrf_token']}).status_code == 401
    with device(app, base_path=prefix) as reopened:
        assert send(reopened, payload, key=key, prefix=prefix).json() == retry.json()
    assert count(app) == 1


def test_disabled_missing_wrong_duplicate_token_and_strict_body(app, client):
    assert send(client).status_code == 404
    with device(app) as client:
        for bad in ({'Content-Type':'application/json'}, dict(HEADERS, **{'X-Fucheng-Report-Token':'wrong'})):
            response = send(client, headers=bad)
            assert response.status_code == 401 and TOKEN not in response.text
        duplicate = list(HEADERS.items()) + [('X-Fucheng-Report-Token', TOKEN)]
        assert send(client, headers=duplicate).status_code == 401
        assert send(client, headers={'X-Fucheng-Report-Token':TOKEN}).status_code == 415
        invalid = report()
        invalid['checks'][0]['unexpected'] = 'do not run'
        assert send(client, invalid).status_code == 422
        for raw in (b'{"schema_version":1,"schema_version":1}', b'{"value":NaN}', b'\xff'):
            assert client.post(f'/api/deployment-reports/{uuid4()}', content=raw, headers=HEADERS).status_code == 422
        assert send(client, key='invalid-uuid').status_code == 422
        assert client.post(f'/api/deployment-reports/{uuid4()}', content=b'x' * 262145, headers=HEADERS).status_code == 413
        # Body protection also applies before authentication, including unknown credentials.
        assert client.post(f'/api/deployment-reports/{uuid4()}', content=b'x' * 262145).status_code == 413
    assert count(app) == 0


@pytest.mark.parametrize('prefix', ['', '/fucheng'])
def test_exact_https_ingress_origin_and_no_privilege_bypass(app, prefix):
    settings = dict(base_path=prefix, public_origin='https://club.example', session_cookie_secure=True,
                    trusted_proxy='172.30.98.3', proxy_kind='local')
    with device(app, **settings) as client:
        # Native sender uses the same authority Origin and trusted ingress identity.
        client.base_url = 'https://club.example'
        client._transport.client = ('172.30.98.3', 12345)
        ingress = {'X-Forwarded-For':'192.0.2.10', 'X-Forwarded-Proto':'https'}
        assert send(client, prefix=prefix, headers=HEADERS | ingress).status_code == 403
        assert send(client, prefix=prefix, headers=HEADERS | ingress | {'Origin':'https://evil.example'}).status_code == 403
        good = HEADERS | ingress | {'Origin':'https://club.example'}
        assert send(client, prefix=prefix, headers=good).status_code == 200
        assert send(client, prefix=prefix, headers=good | {'Host':'evil.example'}).status_code == 400
        assert send(client, prefix=prefix, headers=good | {'X-Forwarded-Proto':'http'}).status_code == 400
    assert count(app) == 1


def test_idempotency_bypasses_full_storage_and_durable_hourly_limit(app):
    payload, key = report(), str(uuid4())
    with device(app, report_upload_max_reports=1) as client:
        first = send(client, payload, key=key)
        assert first.status_code == 200
        assert send(client, payload, key=key).json() == first.json()
        assert send(client).status_code == 507
    with device(app, report_upload_hourly_limit=1) as client:
        assert send(client, payload, key=key).json() == first.json()
        response = send(client)
        assert response.status_code == 429 and response.headers['Retry-After'] == '3600'
    with device(app, report_upload_device_id='another-synthetic-device') as client:
        assert send(client, payload, key=key).status_code == 409
    assert count(app) == 1


def test_byte_cap_preserves_old_reports(app):
    # A pre-existing synthetic row exercises aggregate capacity without 100s of
    # uploads. Production rows can only be inserted through the validated API.
    old = report()
    with app.state.session_factory.begin() as db:
        db.add(DeviceDeploymentReport(report_id=str(uuid4()), device_id='previous-device', digest='0'*64,
               report_json=canonical_report(parse_report(json.dumps(old).encode())), size_bytes=262140,
               received_at=now_utc() - timedelta(days=1)))
    with device(app, report_upload_max_bytes=262144) as client:
        assert send(client).status_code == 507
    assert count(app) == 1


def test_admin_pagination(app, admin_password):
    with device(app) as client:
        ids = []
        for _ in range(3):
            ids.append(send(client).json()['report_id'])
        client.post('/api/auth/login', json={'username':'admin', 'password':admin_password})
        seen, before = [], ''
        for _ in range(3):
            page = client.get('/api/admin/deployment-reports', params={'limit':1, **({'before':before} if before else {})}).json()
            seen.append(page['items'][0]['report_id'])
            before = page['next_before']
        assert len(set(seen)) == 3 and set(seen) == set(ids) and before is None
        assert client.get('/api/admin/deployment-reports', params={'before':str(uuid4())}).status_code == 404
        assert client.get(f'/api/admin/deployment-reports/{uuid4()}/json').status_code == 404


def test_settings_file_only_disabled_default_and_hidden_secret(tmp_path, monkeypatch):
    assert not Settings(database_url='sqlite://').report_upload_enabled
    monkeypatch.setenv('FUCHENG_REPORT_UPLOAD_ENABLED','false')
    monkeypatch.setenv('FUCHENG_REPORT_UPLOAD_TOKEN_FILE','/does-not-exist')
    assert not Settings.from_env().report_upload_enabled
    monkeypatch.setenv('FUCHENG_REPORT_UPLOAD_ENABLED','true')
    monkeypatch.setenv('FUCHENG_REPORT_UPLOAD_DEVICE_ID','club-synthetic-01')
    with pytest.raises(ValueError, match='unavailable or invalid'):
        Settings.from_env()
    path = tmp_path/'token'
    path.write_text(TOKEN + '\n')
    monkeypatch.setenv('FUCHENG_REPORT_UPLOAD_TOKEN_FILE', str(path))
    loaded = Settings.from_env()
    assert loaded.report_upload_token == TOKEN and TOKEN not in repr(loaded)
    for invalid in ('short', 'A'*64, TOKEN + '\n' + TOKEN, 'x'*300):
        path.write_text(invalid)
        with pytest.raises(ValueError):
            Settings.from_env()
    path.unlink()
    import os
    os.mkfifo(path)
    with pytest.raises(ValueError):
        Settings.from_env()


def test_slow_chunked_body_and_in_memory_admission_are_bounded():
    called = False
    async def application(scope, receive, send):
        nonlocal called
        called = True
    limiter = IngressLimiter()
    guard = PublicGuard(application, limiter)
    scope = {'type':'http','path':'/api/deployment-reports/test','method':'POST', 'headers':[], 'client':('synthetic',1)}
    async def scenario():
        messages = []
        async def slow():
            raise TimeoutError
        async def output(message): messages.append(message)
        await guard(scope, slow, output)
        return messages
    messages = asyncio.run(scenario())
    assert messages[0]['status'] == 408 and not called
    limiter.limits = dict(limiter.limits, **{'device-write':(1,0,1,0)})
    assert limiter.allow('device-write','another') is True
    assert limiter.allow('device-write','another') is False


def test_0012_preserves_all_previous_tables_and_enforces_append_only(tmp_path, monkeypatch):
    path = tmp_path/'migration.db'
    monkeypatch.setenv('FUCHENG_DATABASE_URL', f'sqlite:///{path}')
    config = Config('alembic.ini')
    command.upgrade(config, '0002_competition_registration')
    with sqlite3.connect(path) as db:
        db.executescript("""
            INSERT INTO admins VALUES ('a','synthetic-admin','synthetic-hash',1,'2026-01-01');
            INSERT INTO members VALUES ('m','合成會員',NULL,NULL,3,'unset',1,2,'2026-01-01','2026-01-02');
            INSERT INTO login_sessions VALUES ('s','synthetic-token','synthetic-csrf','a','2028-01-01','2026-01-01');
            INSERT INTO member_audits VALUES ('ma','m','a','create','{}','2026-01-01');
            INSERT INTO competitions VALUES ('c','合成場次','2026-01-02',10,'2026-01-01',NULL,'ended',1,2,'2026-01-01','2026-01-01');
            INSERT INTO competition_audits VALUES ('ca','c','a','create','{}',NULL,'2026-01-01');
            INSERT INTO competition_registrations VALUES ('r','c','m','confirmed','unset',3,1,1,'a','a','2026-01-01','2026-01-01');
            INSERT INTO registration_audits VALUES ('ra','r','c','a','create','{}',NULL,'synthetic-request','2026-01-01');
        """)
    command.upgrade(config, '0011_admin_management')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO deployment_reports VALUES (1,1,'{}',?,'a','2026-01-01')", ('0'*64,))
        db.execute("INSERT INTO deployment_report_audits VALUES ('da',1,?,'a','2026-01-01')", ('0'*64,))
        db.commit()
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version' ORDER BY name")]
        columns = {t:[r[1] for r in db.execute(f'PRAGMA table_info("{t}")')] for t in tables}
        before = {t:db.execute(f'SELECT * FROM "{t}" ORDER BY rowid').fetchall() for t in tables}
    command.upgrade(config, 'head')
    command.check(config)
    with sqlite3.connect(path) as db:
        for table in tables:
            projection = ",".join(f'"{column}"' for column in columns[table])
            assert db.execute(f'SELECT {projection} FROM "{table}" ORDER BY rowid').fetchall() == before[table]
        assert db.execute("SELECT registration_mode,doubles_min_total_level FROM competitions").fetchall() == [("individual",None)]
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '0014_doubles_registration'
        assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        after_tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version'")}
        assert after_tables == set(tables) | {'device_deployment_reports','doubles_entries','doubles_entry_members','doubles_audits','doubles_receipts'}
        db.execute('INSERT INTO device_deployment_reports VALUES (?,?,?,?,?,?)', ('r','synthetic-device','0'*64,'{}',2,'2026-01-01'))
        db.commit()
        for sql in ("UPDATE device_deployment_reports SET digest='changed'", 'DELETE FROM device_deployment_reports'):
            with pytest.raises(sqlite3.IntegrityError, match='append-only'):
                db.execute(sql)
        assert db.execute('SELECT COUNT(*) FROM device_deployment_reports').fetchone() == (1,)


def test_kit_allowlist_original_files_and_sender_contract(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('host_report_kit', root/'scripts/host_report_kit.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = tmp_path
    for source in module.FILES:
        target = tmp_path/source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root/source).read_bytes())
    secret = tmp_path/'private/report-upload-token.txt'
    secret.parent.mkdir()
    secret.write_text(TOKEN)
    result = module.create_kit(tmp_path/'data/kit/report.zip')
    assert result['contains_credentials'] is False
    with zipfile.ZipFile(result['archive']) as archive:
        assert set(archive.namelist()) == set(module.FILES.values()) | {'manifest.json','CHECK-AND-SEND.cmd'}
        for name in archive.namelist():
            assert TOKEN.encode() not in archive.read(name)
            if name.endswith('.ps1'): assert archive.read(name).startswith(b'\xef\xbb\xbf')
        manifest = json.loads(archive.read('manifest.json'))
        for name, digest in manifest['files'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    with pytest.raises(FileExistsError): module.create_kit(Path(result['archive']))
    with pytest.raises(ValueError): module.create_kit(tmp_path/'outside.zip')
    sender = (root/'deploy/docker/send-host-report.ps1').read_text(encoding='utf-8-sig')
    assert "$request.AllowAutoRedirect = $false" in sender
    assert "$request.Headers['Origin'] = $target.GetLeftPart([UriPartial]::Authority)" in sender
    assert "$request.Headers['X-Fucheng-Report-Token'] = $token" in sender
    assert 'ServerCertificateValidationCallback' not in sender and 'SkipCertificateCheck' not in sender
    assert 'Write-Status \'unknown\' $null' in sender and 'raw_report_sha256 -cne $rawHash' in sender
    assert sender.index('Write-NewJson $operationPath') < sender.index('$request.BeginGetRequestStream(')
    assert '[IO.FileMode]::CreateNew' in sender
    wrapper = (root/'deploy/docker/check-and-send.ps1').read_text(encoding='utf-8-sig')
    assert wrapper.index("'host-preflight.ps1'") < wrapper.index("'send-host-report.ps1'")
    assert 'ProbeNetwork=(!$SkipNetwork)' in wrapper and 'ImageRef=$ImageRef' in wrapper
