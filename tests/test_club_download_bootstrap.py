"""PowerShell harness: preparation and rejected artifacts never upload or execute."""
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from test_club_host_one_shot import ROOT, PWSH, ps, quote, runner_kit


pytestmark = pytest.mark.skipif(not PWSH, reason='PowerShell runtime unavailable')

def test_prepare_only_creates_same_operation_without_token_or_network(tmp_path):
    kit=runner_kit(tmp_path,token=False)
    source='& SCRIPT -PrepareOnly -DeadlineSeconds 30\nexit $LASTEXITCODE'.replace('SCRIPT',quote(kit/'deploy/docker/club-host-one-shot.ps1'))
    result=ps(tmp_path,source,timeout=40)
    assert result.returncode==0,result.stdout+result.stderr
    workspace=tmp_path/'local data 繁中/FuchengClubHostCheck'
    directory=workspace/json.loads((workspace/'active-report.json').read_text())['directory']
    first=(directory/'upload-operation.json').read_bytes()
    assert not (directory/'upload-status.json').exists() and not (directory/'upload-receipt.json').exists()
    result=ps(tmp_path,source,timeout=40)
    assert result.returncode==0,result.stdout+result.stderr
    assert (directory/'upload-operation.json').read_bytes()==first


def function_source(names):
    return '''$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile(SCRIPT,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'parse errors' }
foreach ($name in NAMES) {
$f=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true)
if (!$f) { throw 'missing function' }
. ([scriptblock]::Create($f.Extent.Text))
}
'''.replace('SCRIPT',quote(ROOT/'deploy/docker/club-host-bootstrap.ps1')).replace('NAMES',"@("+','.join(quote(n) for n in names)+')')


@pytest.mark.parametrize('bad',['traversal','duplicate','symlink','hash'])
def test_zip_rejected_before_any_entry_written(tmp_path,bad):
    archive=tmp_path/'tools.zip'
    contents={'safe.ps1':b'../escape' if bad=='symlink' else b'# safe fixture'}
    manifest={'schema_version':1,'kind':'club-host-one-shot-kit','contains_credentials':False,'files':{'safe.ps1':hashlib.sha256(contents['safe.ps1']).hexdigest()}}
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('manifest.json',json.dumps(manifest))
        if bad=='traversal':z.writestr('../escape.txt','forbidden')
        elif bad=='duplicate':z.writestr('safe.ps1',b'# duplicate')
        elif bad=='symlink':
            info=zipfile.ZipInfo('safe.ps1');info.external_attr=(0o120777<<16);z.writestr(info,'../escape')
        if bad!='symlink':
            for name,value in contents.items():z.writestr(name,value if bad!='hash' else b'changed')
    destination=tmp_path/'output'
    result=ps(tmp_path,function_source(['Expand-VerifiedToolZip'])+'''try { Expand-VerifiedToolZip ARCHIVE DEST;throw 'accepted invalid archive' } catch { if ($_.Exception.Message -eq 'accepted invalid archive') { throw };Write-Output 'rejected' }
'''.replace('ARCHIVE',quote(archive)).replace('DEST',quote(destination)))
    assert result.returncode==0 and 'rejected' in result.stdout,result.stdout+result.stderr
    assert not destination.exists() and not (tmp_path/'escape.txt').exists()


def test_null_gui_prompt_uses_console_then_login_unknown_renew_same_uuid_and_cached_receipt(tmp_path,app,admin_password):
    """Only the native Windows probe and interactive prompt use deterministic doubles."""
    import base64
    from dataclasses import replace
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import importlib.util
    import re
    import ssl
    import subprocess
    from threading import Thread
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select
    from fucheng.app import create_app
    from fucheng.models import LoginSession, DeviceDeploymentReport
    from test_device_reports import TOKEN

    paths=[];uploads=[];drop=[True]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_args):pass
        def do_GET(self):self.dispatch()
        def do_POST(self):self.dispatch()
        def dispatch(self):
            paths.append(self.path)
            raw=self.rfile.read(int(self.headers.get('Content-Length','0')))
            headers={name:value for name,value in self.headers.items() if name.lower() in {'cookie','origin','x-csrf-token','content-type','x-fucheng-report-token'}}
            client.cookies.clear()
            response=client.request(self.command,self.path,content=raw,headers=headers)
            if self.path.startswith('/api/deployment-reports/'):
                uploads.append((self.path,raw))
                if drop[0]:
                    drop[0]=False
                    self.connection.shutdown(2);self.connection.close();return
            self.send_response(response.status_code)
            for name in ('set-cookie','content-type'):
                if name in response.headers:self.send_header(name,response.headers[name])
            self.send_header('Content-Length',str(len(response.content)));self.end_headers()
            self.wfile.write(response.content)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    cert=tmp_path/'cert.pem';key=tmp_path/'key.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],check=True,capture_output=True)
    tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(cert,key)
    server.socket=tls.wrap_socket(server.socket,server_side=True)
    thread=Thread(target=server.serve_forever,daemon=True)
    endpoint=f'https://localhost:{server.server_port}/api/deployment-reports'
    spec=importlib.util.spec_from_file_location('integrated_package',ROOT/'scripts/club_host_one_shot_package.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    source_root=tmp_path/'source';builder.ROOT=source_root;builder.ENDPOINT=endpoint;builder.DEVICE_ID='club-synthetic-01'
    for source in set(builder.FILES)|builder.DOWNLOAD_SOURCES:
        path=source_root/source;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((ROOT/source).read_bytes())
    fixture=runner_kit(tmp_path/'probe-fixture',endpoint,token=False)
    (source_root/'deploy/docker/host-preflight.ps1').write_bytes((fixture/'deploy/docker/host-preflight.ps1').read_bytes())
    helper=source_root/'deploy/docker/club-host-credential.ps1'
    helper_text=helper.read_text(encoding='utf-8-sig').replace("'^https://momonong\\.me/fucheng/api/deployment-reports$'",quote('^'+re.escape(endpoint)+'$'))
    helper.write_text(helper_text,encoding='utf-8-sig')
    # The old GUI returns null, as observed on site; only console input is doubled.
    # The real
    # credential script still performs real TLS login, CSRF issuance and logout.
    bootstrap_source=source_root/'deploy/docker/club-host-bootstrap.ps1'
    text=bootstrap_source.read_text(encoding='utf-8-sig')
    begin=text.index('function Invoke-CredentialHelper(');end=text.index('function Invoke-RunnerHelper(',begin)
    encoded=base64.b64encode(admin_password.encode()).decode()
    prompt_counter=tmp_path/'prompt-count.txt'
    replacement="""function Invoke-CredentialHelper([string]$Script,[string]$ReportDirectory,[string]$ConfigFile) {
    function Get-Credential { return $null }
    function Read-Host {
        param($Prompt,[switch]$AsSecureString)
        if (!$AsSecureString) { return 'admin' }
        [IO.File]::AppendAllText(COUNTER,'prompt\n')
        return ConvertTo-SecureString ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('PASSWORD'))) -AsPlainText -Force
    }
    & $Script -ReportDirectory $ReportDirectory -ConfigFile $ConfigFile
    if ($LASTEXITCODE -ne 0) { throw 'fixture credential failure' }
}
""".replace('COUNTER',quote(prompt_counter)).replace('PASSWORD',encoded)
    bootstrap_source.write_text(text[:begin]+replacement+text[end:],encoding='utf-8-sig')
    output=source_root/'data/download';builder.create_download_bundle(output)
    application=create_app(replace(app.state.settings,host_tools_dir=output,report_upload_enabled=True,report_upload_token=TOKEN,report_upload_device_id='club-synthetic-01'))
    launcher=(output/'launcher.ps1').read_text(encoding='utf-8-sig')
    try:
        with TestClient(application,base_url=endpoint.removesuffix('/api/deployment-reports')) as client:
            thread.start()
            first=ps(tmp_path,launcher,timeout=45,env={'SSL_CERT_FILE':str(cert)})
            assert admin_password not in first.stdout+first.stderr and TOKEN not in first.stdout+first.stderr
            assert len(uploads)==1,first.stdout+first.stderr+str(paths)
            workspace=tmp_path/'local data 繁中/FuchengClubHostCheck'
            directory=workspace/json.loads((workspace/'active-report.json').read_text())['directory']
            operation=(directory/'upload-operation.json').read_bytes()
            assert not (directory/'upload-receipt.json').exists()
            # Force credential expiry; renewal must retain the original UUID/body.
            with application.state.session_factory.begin() as db:
                from fucheng.models import Admin
                db.scalar(select(Admin)).version+=1
            retry=ps(tmp_path,launcher,timeout=45,env={'SSL_CERT_FILE':str(cert)})
            assert (directory/'upload-receipt.json').exists(),retry.stdout+retry.stderr
            assert (directory/'upload-operation.json').read_bytes()==operation
            assert len(uploads)==2 and uploads[0]==uploads[1]
            cached=ps(tmp_path,launcher,timeout=45,env={'SSL_CERT_FILE':str(cert)})
            assert len(uploads)==2 and prompt_counter.read_text().splitlines()==['prompt','prompt'],cached.stdout+cached.stderr
            assert paths.count('/api/auth/login')==paths.count('/api/auth/logout')==2
            with application.state.session_factory() as db:
                assert db.scalar(select(func.count()).select_from(LoginSession))==0
                assert db.scalar(select(func.count()).select_from(DeviceDeploymentReport))==1
            for result in (first,retry,cached):
                assert admin_password not in result.stdout+result.stderr and TOKEN not in result.stdout+result.stderr
                assert 'fcr1.' not in result.stdout+result.stderr
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
        application.state.engine.dispose()


@pytest.mark.parametrize('mode',['wrong_hash','redirect'])
def test_launcher_rejects_bad_hash_or_redirect_without_execution(tmp_path,mode):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import ssl
    import subprocess
    from threading import Thread
    marker=tmp_path/'must-not-execute.txt'
    verified=("[IO.File]::WriteAllText("+quote(marker)+",'executed')").encode()
    paths=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_args):pass
        def do_GET(self):
            paths.append(self.path)
            self.send_response(307 if mode=='redirect' else 200)
            if mode=='redirect':self.send_header('Location','/must-never-follow')
            content=verified+b' # changed'
            self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    cert=tmp_path/'cert.pem';key=tmp_path/'key.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],check=True,capture_output=True)
    tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(cert,key);server.socket=tls.wrap_socket(server.socket,server_side=True)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    source=(ROOT/'deploy/docker/club-host-download-launcher.ps1').read_text(encoding='utf-8-sig').replace('@@BOOTSTRAP_URL@@',f'https://localhost:{server.server_port}/bootstrap.ps1').replace('@@BOOTSTRAP_SHA256@@',hashlib.sha256(verified).hexdigest())
    try:
        result=ps(tmp_path,source,env={'SSL_CERT_FILE':str(cert)})
        assert result.returncode==0 and '尚未完成' in result.stdout
        assert paths==['/bootstrap.ps1'] and not marker.exists()
    finally:server.shutdown();server.server_close();thread.join(timeout=5)


def test_console_error_does_not_echo_alphanumeric_secret_fqid(tmp_path):
    from test_deployment_report import report
    kit=runner_kit(tmp_path,token=False)
    scripts=kit/'deploy/docker'
    for name in ('club-host-credential.ps1','club-host-network.ps1'):
        (scripts/name).write_bytes((ROOT/'deploy/docker'/name).read_bytes())
    directory=kit/'data/original';directory.mkdir(parents=True)
    (directory/'upload-operation.json').write_text(json.dumps({'report_id':'11111111-1111-4111-8111-111111111111','endpoint':'https://momonong.me/fucheng/api/deployment-reports','device_id':'club-synthetic-01'}))
    config=kit/'private/club-report.json';value=json.loads(config.read_text());value['endpoint']='https://momonong.me/fucheng/api/deployment-reports';config.write_text(json.dumps(value))
    result=ps(tmp_path,"function Read-Host { param($Prompt,[switch]$AsSecureString); throw 'ALNUM_SECRET_SENTINEL_123' }\n& SCRIPT -ReportDirectory DIRECTORY -ConfigFile CONFIG\n".replace('SCRIPT',quote(scripts/'club-host-credential.ps1')).replace('DIRECTORY',quote(directory)).replace('CONFIG',quote(config)))
    assert 'ALNUM_SECRET_SENTINEL_123' not in result.stdout+result.stderr
    assert 'stage=username' in result.stdout
    assert 'type=System.Management.Automation.RuntimeException' in result.stdout
