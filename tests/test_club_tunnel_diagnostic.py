"""Offline fault classification and bounded tunnel lifecycle diagnostic contracts."""
import json
import pytest
from test_club_host_one_shot import ROOT,PWSH,ps,quote

SCRIPT=ROOT/'deploy/docker/club-tunnel-diagnostic.ps1'
pytestmark=pytest.mark.skipif(not PWSH,reason='PowerShell runtime unavailable')

def functions():
    return """$ErrorActionPreference='Stop';$t=$null;$e=$null
$a=[Management.Automation.Language.Parser]::ParseFile(SCRIPT,[ref]$t,[ref]$e)
if($e.Count){throw 'parse'}
foreach($f in $a.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$true)){. ([scriptblock]::Create($f.Extent.Text))}
""".replace('SCRIPT',quote(SCRIPT))

@pytest.mark.parametrize('status,body,expected,cfcode',[(502,'upstream unavailable','HTTP_502',None),(530,'<span>Error</span><span>1033</span>','HTTP_530',1033),(530,'Error code: 1016','HTTP_530',1016),(302,'do not print this','REDIRECT_REFUSED',None),(200,'{"nonce":"wrong"}','NONCE_MISMATCH',None),(200,'{"nonce":"fixture"}','NONCE_OK',None)])
def test_safe_http_classification(tmp_path,status,body,expected,cfcode):
    assert SCRIPT.exists()
    result=ps(tmp_path,functions()+"$r=Classify-DiagHttp STATUS ([Text.Encoding]::UTF8.GetBytes(BODY)) 'fixture' $true\nWrite-Output ($r|ConvertTo-Json -Compress)".replace('STATUS',str(status)).replace('BODY',quote(body)))
    assert result.returncode==0,result.stdout+result.stderr
    value=json.loads(result.stdout);assert value['outcome']==expected and value['cf_error_code']==cfcode
    assert 'do not print this' not in result.stdout

@pytest.mark.parametrize('kind',['dns','tls','timeout'])
def test_exception_chain_never_prints_messages(tmp_path,kind):
    expr={'dns':"New-Object Net.Sockets.SocketException([int][Net.Sockets.SocketError]::HostNotFound)",'tls':"New-Object Security.Authentication.AuthenticationException('SECRET_SENTINEL_123')",'timeout':"New-Object TimeoutException('SECRET_SENTINEL_123')"}[kind]
    result=ps(tmp_path,functions()+"$x=EXPR\n$outer=New-Object Exception('SECRET_SENTINEL_123',$x)\nWrite-Output ((Get-DiagError $outer)|ConvertTo-Json -Depth 6 -Compress)".replace('EXPR',expr))
    assert result.returncode==0 and 'SECRET_SENTINEL_123' not in result.stdout+result.stderr,result.stdout+result.stderr
    assert json.loads(result.stdout)['category']==kind


def test_url_issued_before_late_registration(tmp_path):
    result=ps(tmp_path,functions()+"""
$script:reads=0
function Invoke-ProbeDocker { $script:reads++;$s=if($script:reads -eq 1){'https://fixture-late.trycloudflare.com ERR lookup timeout x509 connection refused failed to connect SECRET_LOG_SENTINEL'}else{'Registered tunnel connection protocol=http2'};return @{exit_code=0;timed_out=$false;stdout=$s;stderr=''} }
function Start-Sleep {}
$s=[pscustomobject]@{tunnel='fixture-tunnel'}
$early=Wait-DiagTunnel $s $false 3 0
$later=Wait-DiagTunnel $s $true 3 0 $early.origin
Write-Output (@{early=$early;later=$later;reads=$script:reads}|ConvertTo-Json -Depth 6 -Compress)
""")
    assert result.returncode==0,result.stdout+result.stderr
    value=json.loads(result.stdout)
    assert value['early']['origin'] and not value['early']['registered'] and value['later']['registered'] and value['reads']==2
    assert all(value['early']['log_signals'].values()) and 'SECRET_LOG_SENTINEL' not in result.stdout


def test_foreign_cleanup_is_refused(tmp_path):
    result=ps(tmp_path,functions()+"""
$script:removed=$false
function Invoke-ProbeDocker([string[]]$Arguments,[int]$Limit=10){if($Arguments -contains 'rm'){$script:removed=$true};return @{exit_code=0;stdout='foreign';stderr='';timed_out=$false}}
$s=[pscustomobject]@{run_id='11111111-1111-4111-8111-111111111111';probe='fixture-probe';tunnel='fixture-tunnel';network='fixture-net'}
if((Remove-ProbeResources $s) -or $script:removed){throw 'foreign cleanup'}
Write-Output 'PASS'
""")
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('registered',[True,False])
def test_complete_inline_entrypoint_saves_sanitized_steps_and_owned_cleanup(tmp_path,registered):
    fake=tmp_path/'docker.exe';fake.write_text('synthetic executable marker')
    local=tmp_path/'local data 繁中'
    for folder in ('FuchengClubHostCheck','FuchengDeploymentCheck','FuchengDeploymentCheckConsole'):
        d=local/folder;d.mkdir(parents=True);(d/'original.txt').write_text('keep')
    source=SCRIPT.read_text(encoding='utf-8-sig')
    overrides="""function Get-Command([string]$Name){if($Name -ceq 'docker.exe'){return [pscustomobject]@{Source=DOCKER}};return $null}
function Start-Sleep {}
function Start-ProbeWatchdog {return $null}
function Test-DiagOrigin {return @{http_status=200;nonce_match=$true;dns_resolved=$true;error_type=$null}}
function Resolve-DiagDns {return @{resolved=$true;ipv4=$true;ipv6=$false;error=$null}}
function Invoke-DiagHttps {return @{http_status=200;outcome='NONCE_OK';nonce_match=$true;elapsed_ms=1;error=$null}}
$script:logReads=0;$script:removed=0
function Invoke-ProbeDocker([string[]]$Arguments,[int]$Limit=10){
 $out=''
 if($Arguments[0] -eq 'image'){$out='linux|amd64'}
 elseif($Arguments[0] -eq 'logs'){$script:logReads++;$out=if($script:logReads -eq 1){'https://fixture-secret.trycloudflare.com'}else{'LATER_LOG'}}
 elseif($Arguments[0] -eq 'inspect'){$out=if(($Arguments -join ' ') -like '*OOMKilled*'){'running|0|false'}else{('a'*64)+'|'+$state.run_id+'|nonce-only-v1'}}
 elseif($Arguments -contains 'rm'){$script:removed++}
 return @{exit_code=0;stdout=$out;stderr='';timed_out=$false}
}
""".replace('DOCKER',quote(fake)).replace('LATER_LOG','Registered tunnel connection protocol=http2' if registered else 'ERR lookup timeout')
    source=source.replace("$steps=New-Object 'System.Collections.Generic.List[object]'",overrides+"$steps=New-Object 'System.Collections.Generic.List[object]'",1)
    result=ps(tmp_path,source,timeout=20)
    assert result.returncode==0 and not result.stderr,result.stdout+result.stderr
    roots=list((local/'FuchengTunnelDiagnostic').glob('run-*'));assert len(roots)==1
    report=json.loads((roots[0]/'diagnostic.json').read_text())
    rows={entry['stage']:entry['data'] for entry in report['steps']}
    assert rows['summary']['later_nonce_matches']==6 and rows['registration']['registered']==registered
    assert not rows['url_issued']['registered'] and rows['early_https']['sample']['nonce_match']
    assert rows['cleanup']['confirmed'] and 'fixture-secret' not in result.stdout+json.dumps(report)
    assert len([entry for entry in report['steps'] if entry['stage'].startswith('later_https_')])==6
    for folder in ('FuchengClubHostCheck','FuchengDeploymentCheck','FuchengDeploymentCheckConsole'):
        assert (local/folder/'original.txt').read_text()=='keep'


@pytest.mark.parametrize('mode',['nonce','cf530','slow_body','untrusted_tls'])
def test_real_send_and_bounded_body_with_tls_fixture(tmp_path,mode):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    import ssl,subprocess,time
    from threading import Thread
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            calls.append(self.path)
            body=b'<span>Error</span><span>1033</span>' if mode=='cf530' else b'{"nonce":"fixture"}'
            self.send_response(530 if mode=='cf530' else 200);self.send_header('Content-Length',str(len(body)));self.send_header('CF-Ray','fixture');self.end_headers()
            try:
                if mode=='slow_body':self.wfile.write(body[:1]);self.wfile.flush();time.sleep(10);self.wfile.write(body[1:])
                else:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError,ssl.SSLError):pass
    cert=tmp_path/'cert.pem';key=tmp_path/'key.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],check=True,capture_output=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(cert,key);server.socket=tls.wrap_socket(server.socket,server_side=True)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        invoke=functions()+"""
# Only this synthetic harness admits localhost; production Quick Tunnel guard stays exact.
$d=(Get-Command Invoke-DiagHttps).Definition
$d=$d.Replace('^https://[a-z0-9]+(?:-[a-z0-9]+)*\\.trycloudflare\\.com$','^https://localhost:[0-9]+$')
Set-Item function:Invoke-DiagHttps -Value ([scriptblock]::Create($d))
$r=Invoke-DiagHttps ORIGIN 'fixture'
Write-Output ($r|ConvertTo-Json -Depth 8 -Compress)
""".replace('ORIGIN',quote(f'https://localhost:{server.server_port}'))
        result=ps(tmp_path,invoke,timeout=15,env={'SSL_CERT_FILE':'' if mode=='untrusted_tls' else str(cert)})
        assert result.returncode==0,result.stdout+result.stderr
        value=json.loads(result.stdout)
        if mode=='nonce':assert value['outcome']=='NONCE_OK' and value['http_status']==200 and value['nonce_match']
        elif mode=='cf530':assert value['http_status']==530 and value['cf_error_code']==1033 and value['outcome']=='HTTP_530'
        elif mode=='slow_body':
            assert value['http_status']==200 and not value['nonce_match'] and value['error']['category']=='timeout'
            assert 7500<=value['elapsed_ms']<=10500
        else:assert value['http_status'] is None and value['error']['category']=='tls'
        assert '<span>' not in result.stdout and '"nonce":"fixture"' not in result.stdout
        assert calls==([] if mode=='untrusted_tls' else ['/probe/fixture'])
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
