"""Real PowerShell sender transport against a private, trusted TLS fixture.

Use FUCHENG_TEST_PWSH for the verified portable runtime. This does not establish
Windows PowerShell 5.1, Windows-native checks or physical club-host acceptance.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from fucheng.app import create_app
from test_deployment_report import report
from test_device_reports import TOKEN, count

ROOT = Path(__file__).resolve().parents[1]
PWSH = os.environ.get('FUCHENG_TEST_PWSH') or shutil.which('pwsh')
pytestmark = pytest.mark.skipif(not PWSH, reason='PowerShell runtime unavailable; native sender transport NOT_TESTED')


@contextmanager
def tls_receiver(tmp_path, app, mode='normal'):
    key, cert = tmp_path/'tls-key.pem', tmp_path/'tls-cert.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),
                    '-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],
                   check=True,capture_output=True)
    application = create_app(replace(app.state.settings, report_upload_enabled=True,
        report_upload_token=TOKEN, report_upload_device_id='club-synthetic-01'))
    attempts = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args): pass
        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            attempts.append({'path':self.path, 'body':raw, 'origin':self.headers.get('Origin')})
            if mode == 'redirect':
                self.send_response(307)
                self.send_header('Location', '/must-never-follow')
                self.end_headers()
                return
            if mode == 'reject':
                self.send_response(401)
                self.end_headers()
                self.wfile.write(('never-print-' + TOKEN).encode())
                return
            result = client.post(self.path, content=raw, headers={
                'Content-Type':'application/json', 'X-Fucheng-Report-Token':self.headers.get('X-Fucheng-Report-Token','')})
            if mode == 'drop_once' and len(attempts) == 1:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            content = result.content
            if mode == 'invalid_receipt': content = b'{"unsafe":"never-print-server-body"}'
            self.send_response(result.status_code)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(content)))
            self.end_headers()
            self.wfile.write(content)
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert,key)
    server.socket = context.wrap_socket(server.socket,server_side=True)
    thread = Thread(target=server.serve_forever,daemon=True)
    with TestClient(application) as client:
        thread.start()
        try:
            yield f'https://localhost:{server.server_port}/api/deployment-reports', cert, attempts
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    application.state.engine.dispose()


def sender(tmp_path, endpoint, cert, *, existing=None, wrapper=False, trust=True):
    kit = tmp_path/'kit'
    scripts = kit/'deploy/docker'
    scripts.mkdir(parents=True,exist_ok=True)
    for name in ('send-host-report.ps1','check-and-send.ps1'):
        shutil.copyfile(ROOT/'deploy/docker'/name,scripts/name)
    private = kit/'private'
    private.mkdir(exist_ok=True)
    token = private/'token.txt'
    token.write_text(TOKEN)
    config = private/'club-report.json'
    config.write_text(json.dumps({'endpoint':endpoint,'device_id':'club-synthetic-01','token_file':'token.txt'}))
    directory = existing or kit/'data/fixture-report'
    if not existing:
        if wrapper:
            # A deterministic host-probe fixture exercises the real wrapper's
            # production call order/parameter handoff without claiming Linux can
            # execute Get-CimInstance or Windows-specific checks.
            source = kit/'fixture.json'
            source.write_text(json.dumps(report()))
            fake = '''param([string]$OutputDir,[switch]$ProbeNetwork,[string]$BasePath,[string]$ImageRef)
$ErrorActionPreference='Stop'
if (!$ProbeNetwork -or $ImageRef -notmatch '@sha256:[0-9a-f]{64}$') { throw 'wrapper probe/image contract' }
New-Item -ItemType Directory -Path $OutputDir | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../../fixture.json') -Destination (Join-Path $OutputDir 'report.json')
[IO.File]::WriteAllText((Join-Path $OutputDir 'report.md'),'synthetic fixture, not Windows evidence')
'''
            (scripts/'host-preflight.ps1').write_text(fake,encoding='utf-8-sig')
        else:
            directory.mkdir(parents=True)
            (directory/'report.json').write_text(json.dumps(report()))
            (directory/'report.md').write_text('synthetic fixture')
    args = [str(PWSH),'-NoProfile','-NonInteractive','-File',str(scripts/('check-and-send.ps1' if wrapper else 'send-host-report.ps1'))]
    args += (['-RetryReportDirectory',str(directory)] if wrapper and existing else
             ['-OutputDir',str(directory)] if wrapper else ['-ReportDirectory',str(directory)])
    args += ['-ConfigFile',str(config)]
    env = os.environ | {'POWERSHELL_TELEMETRY_OPTOUT':'1','POWERSHELL_UPDATECHECK':'Off','DOTNET_CLI_TELEMETRY_OPTOUT':'1',
        'XDG_CACHE_HOME':str(tmp_path/'cache'),'XDG_CONFIG_HOME':str(tmp_path/'config'),'XDG_DATA_HOME':str(tmp_path/'xdg-data')}
    if trust: env['SSL_CERT_FILE'] = str(cert)
    result = subprocess.run(args,env=env,text=True,capture_output=True,timeout=45)
    assert TOKEN not in result.stdout + result.stderr
    assert 'never-print-' not in result.stdout + result.stderr
    return result, directory


def test_actual_wrapper_fixture_then_sender_and_cached_receipt(tmp_path,app):
    with tls_receiver(tmp_path,app) as (endpoint,cert,attempts):
        result,directory = sender(tmp_path,endpoint,cert,wrapper=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (directory/'report.json').is_file() and (directory/'report.md').is_file()
        operation = (directory/'upload-operation.json').read_bytes()
        saved = json.loads((directory/'upload-receipt.json').read_text(encoding='utf-8-sig'))
        assert saved['report_id'] == json.loads(operation)['report_id']
        assert json.loads((directory/'upload-status.json').read_text())['state'] == 'received'
        again,_ = sender(tmp_path,endpoint,cert,existing=directory,wrapper=True)
        assert again.returncode == 0 and len(attempts) == 1
        assert (directory/'upload-operation.json').read_bytes() == operation
        assert attempts[0]['origin'] == endpoint.split('/api/')[0]
        assert count(app) == 1


def test_actual_lost_response_same_id_retry_recovers_one_receipt(tmp_path,app):
    with tls_receiver(tmp_path,app,'drop_once') as (endpoint,cert,attempts):
        first,directory = sender(tmp_path,endpoint,cert)
        assert first.returncode == 4, first.stdout + first.stderr
        operation = (directory/'upload-operation.json').read_bytes()
        assert not (directory/'upload-receipt.json').exists()
        assert json.loads((directory/'upload-status.json').read_text())['state'] == 'unknown'
        retry,_ = sender(tmp_path,endpoint,cert,existing=directory)
        assert retry.returncode == 0, retry.stdout + retry.stderr
        assert (directory/'upload-operation.json').read_bytes() == operation
        assert attempts[0]['path'] == attempts[1]['path'] and attempts[0]['body'] == attempts[1]['body']
        assert count(app) == 1


@pytest.mark.parametrize('mode,exitcode', [('redirect',3),('reject',3),('invalid_receipt',4)])
def test_actual_redirect_rejection_and_bad_receipt_never_expose_body(tmp_path,app,mode,exitcode):
    with tls_receiver(tmp_path,app,mode) as (endpoint,cert,attempts):
        result,directory = sender(tmp_path,endpoint,cert)
        assert result.returncode == exitcode, result.stdout + result.stderr
        assert len(attempts) == 1
        assert not (directory/'upload-receipt.json').exists()
        original = (directory/'upload-operation.json').read_bytes()
        payload = json.loads((directory/'report.json').read_text())
        payload['host']['name'] = 'changed-original'
        (directory/'report.json').write_text(json.dumps(payload))
        again,_ = sender(tmp_path,endpoint,cert,existing=directory)
        assert again.returncode == 2 and len(attempts) == 1
        assert (directory/'upload-operation.json').read_bytes() == original


def test_actual_untrusted_tls_is_unknown_without_request_or_bypass(tmp_path,app):
    with tls_receiver(tmp_path,app) as (endpoint,cert,attempts):
        result,directory = sender(tmp_path,endpoint,cert,trust=False)
        assert result.returncode == 4, result.stdout + result.stderr
        assert len(attempts) == 0 and count(app) == 0
        assert not (directory/'upload-receipt.json').exists()
