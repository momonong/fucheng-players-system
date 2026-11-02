"""QUIC registration, live readiness, and isolated full-entry diagnostic fixtures."""
import json
import pytest
from test_club_host_one_shot import ROOT,PWSH,ps,quote

SCRIPT=ROOT/'deploy/docker/club-quic-diagnostic.ps1'
pytestmark=pytest.mark.skipif(not PWSH,reason='PowerShell runtime unavailable')

def functions():
    return """$ErrorActionPreference='Stop';$t=$null;$e=$null
$a=[Management.Automation.Language.Parser]::ParseFile(SCRIPT,[ref]$t,[ref]$e)
if($e.Count){throw 'parse'}
foreach($f in $a.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$true)){. ([scriptblock]::Create($f.Extent.Text))}
""".replace('SCRIPT',quote(SCRIPT))

@pytest.mark.parametrize('logs,registered,http2',[
    ('Registered tunnel connection connIndex=0 protocol=quic',True,False),
    ('Registered tunnel connection connIndex=0 protocol=http2',False,True),
    ('https://fixture.trycloudflare.com',False,False),
    ('Failed to register tunnel connection protocol=quic ERR timeout SECRET_RAW_LOG',False,False),
    ('Registering tunnel connection protocol=quic',False,False),
])
def test_only_explicit_quic_registration_counts(tmp_path,logs,registered,http2):
    assert SCRIPT.exists()
    result=ps(tmp_path,functions()+"""
function Invoke-ProbeDocker {return @{exit_code=0;timed_out=$false;stdout=LOGS;stderr=''}}
function Start-Sleep {}
$r=Wait-DiagTunnel ([pscustomobject]@{tunnel='fixture-tunnel'}) $true 1 0 'https://fixture.trycloudflare.com'
$r.Remove('origin');Write-Output ($r|ConvertTo-Json -Depth 6 -Compress)
""".replace('LOGS',quote(logs)))
    assert result.returncode==0,result.stdout+result.stderr
    value=json.loads(result.stdout);assert value['registered']==registered and value['http2_registered']==http2
    assert 'SECRET_RAW_LOG' not in result.stdout

@pytest.mark.parametrize('registered,ready_status,http2,container,expected',[(True,200,False,'running','PASS'),(True,503,False,'running','WARN'),(False,200,False,'running','NOT_CONFIRMED'),(False,200,True,'running','FAIL'),(True,200,False,'exited','WARN')])
def test_stale_registration_without_current_ready_never_claims_active(tmp_path,registered,ready_status,http2,container,expected):
    result=ps(tmp_path,functions()+"""
$r=Get-QuicResult REG @{ready=READY;http_status=STATUS;active_connections=COUNT} @{known=$true;state=STATE} OTHER
Write-Output ($r|ConvertTo-Json -Compress)
""".replace('REG','$true' if registered else '$false').replace('READY','$true' if ready_status==200 else '$false').replace('STATUS',str(ready_status)).replace('COUNT','1' if ready_status==200 else '0').replace('STATE',quote(container)).replace('OTHER','$true' if http2 else '$false'))
    assert result.returncode==0,result.stdout+result.stderr
    value=json.loads(result.stdout);assert value['status']==expected and value['active_at_final_check']==(expected=='PASS')
    assert value['workers_vpc_end_to_end']=='NOT_TESTED'

@pytest.mark.parametrize('status,body,expected',[(530,'<span>Error</span><span>1033</span>','HTTP_530'),(502,'not printed RAW_BODY_SENTINEL','HTTP_502'),(302,'not printed RAW_BODY_SENTINEL','REDIRECT_REFUSED')])
def test_safe_http_errors_remain_distinct(tmp_path,status,body,expected):
    result=ps(tmp_path,functions()+"Write-Output ((Classify-DiagHttp STATUS ([Text.Encoding]::UTF8.GetBytes(BODY)) 'fixture' $true)|ConvertTo-Json -Compress)".replace('STATUS',str(status)).replace('BODY',quote(body)))
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)['outcome']==expected and 'RAW_BODY_SENTINEL' not in result.stdout


def test_cleanup_refuses_foreign_resources(tmp_path):
    result=ps(tmp_path,functions()+"""
$script:removed=$false
function Invoke-ProbeDocker([string[]]$Arguments,[int]$Limit=10){if($Arguments -contains 'rm'){$script:removed=$true};return @{exit_code=0;stdout='foreign';stderr='';timed_out=$false}}
$s=[pscustomobject]@{run_id='11111111-1111-4111-8111-111111111111';probe='fixture-probe';tunnel='fixture-tunnel';network='fixture-net'}
if((Remove-ProbeResources $s) -or $script:removed){throw 'foreign cleanup'}
Write-Output 'PASS'
""")
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('mode,expected',[('quic','PASS'),('http2','FAIL'),('url_only','NOT_CONFIRMED'),('disconnected','WARN')])
def test_complete_inline_force_quic_and_current_readiness(tmp_path,mode,expected):
    fake=tmp_path/'docker.exe';fake.write_text('synthetic marker')
    local=tmp_path/'local data 繁中'
    for folder in ('FuchengClubHostCheck','FuchengDeploymentCheck','FuchengDeploymentCheckConsole','FuchengTunnelDiagnostic'):
        d=local/folder;d.mkdir(parents=True);(d/'original.txt').write_text('keep')
    source=SCRIPT.read_text(encoding='utf-8-sig')
    assert "'--protocol','quic'" in source and "'--protocol','http2'" not in source and "'--protocol','auto'" not in source
    assert not any(text in source for text in ('Get-Credential','Read-Host','/auth/','report-upload-token','upload-operation'))
    log={'quic':'Registered tunnel connection connIndex=0 protocol=quic','http2':'Registered tunnel connection connIndex=0 protocol=http2','url_only':'ERR timeout failed to register protocol=quic RAW_LOG_SECRET','disconnected':'Registered tunnel connection connIndex=0 protocol=quic\nConnection terminated connIndex=0 error=RAW_LOG_SECRET'}[mode]
    overrides="""function Get-Command([string]$Name){if($Name -ceq 'docker.exe'){return [pscustomobject]@{Source=DOCKER}};return $null}
function Start-Sleep {}
function Start-ProbeWatchdog {return $null}
function Test-DiagOrigin {return @{http_status=200;nonce_match=$true;dns_resolved=$true;error_type=$null}}
function Resolve-DiagDns {return @{resolved=$true;ipv4=$true;ipv6=$false;error=$null}}
function Invoke-DiagHttps {return @{http_status=200;outcome='NONCE_OK';nonce_match=$true;elapsed_ms=1;error=$null}}
function Test-DiagReady {return @{ready=READY;http_status=STATUS;active_connections=COUNT;error_type=$null}}
$script:runs=New-Object 'System.Collections.Generic.List[object]';$script:removed=0
function Invoke-ProbeDocker([string[]]$Arguments,[int]$Limit=10){
 $out=''
 if($Arguments[0] -eq 'image'){$out='linux|amd64'}
 elseif($Arguments[0] -eq 'run'){$script:runs.Add(@($Arguments))}
 elseif($Arguments[0] -eq 'logs'){$out="https://hidden-fixture.trycloudflare.com`n"+LOGS}
 elseif($Arguments[0] -eq 'inspect'){$out=if(($Arguments -join ' ') -like '*OOMKilled*'){'running|0|false'}else{('a'*64)+'|'+$state.run_id+'|nonce-only-v1'}}
 elseif($Arguments -contains 'rm'){$script:removed++}
 return @{exit_code=0;stdout=$out;stderr='';timed_out=$false}
}
""".replace('DOCKER',quote(fake)).replace('LOGS',quote(log)).replace('READY','$true' if mode in ('quic','http2') else '$false').replace('STATUS','200' if mode in ('quic','http2') else '503').replace('COUNT','1' if mode in ('quic','http2') else '0')
    source=source.replace("$steps=New-Object 'System.Collections.Generic.List[object]'",overrides+"$steps=New-Object 'System.Collections.Generic.List[object]'",1)
    calls=tmp_path/'runs.json'
    result=ps(tmp_path,source+"\n[IO.File]::WriteAllText("+quote(calls)+",(@{runs=$script:runs.ToArray();removed=$script:removed}|ConvertTo-Json -Depth 8))",timeout=20)
    assert result.returncode==0 and not result.stderr,result.stdout+result.stderr
    roots=list((local/'FuchengQuicDiagnostic').glob('run-*'));assert len(roots)==1
    report=json.loads((roots[0]/'diagnostic.json').read_text());rows={entry['stage']:entry['data'] for entry in report['steps']}
    assert rows['summary']['status']==expected and rows['summary']['active_at_final_check']==(expected=='PASS')
    assert rows['summary']['later_nonce_matches']==6 and rows['summary']['workers_vpc_end_to_end']=='NOT_TESTED'
    assert rows['account_scope']['http2_fallback_allowed'] is False
    assert '公開 HTTPS 隨機字串核對：6 / 6' in result.stdout
    assert rows['cleanup']['confirmed'] and all(value not in result.stdout+json.dumps(report) for value in ('hidden-fixture','RAW_LOG_SECRET'))
    commands=json.loads(calls.read_text());assert commands['removed']==3 and len(commands['runs'])==2
    tunnel=commands['runs'][1];assert tunnel[tunnel.index('--protocol')+1]=='quic' and tunnel[tunnel.index('--metrics')+1]=='0.0.0.0:20241'
    assert all(not(set(args)&{'-v','--volume','--mount','-p','--publish','--privileged','--network=host'}) for args in commands['runs'])
    for folder in ('FuchengClubHostCheck','FuchengDeploymentCheck','FuchengDeploymentCheckConsole','FuchengTunnelDiagnostic'):
        assert (local/folder/'original.txt').read_text()=='keep'


@pytest.mark.parametrize('status,count,expected',[(200,1,True),(503,0,False),(200,0,False)])
def test_real_ready_client_reads_only_safe_fields(tmp_path,status,count,expected):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from threading import Thread
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            body=json.dumps({'status':status,'readyConnections':count,'connectorId':'MUST_NOT_PRINT_CONNECTOR'}).encode()
            self.send_response(status);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    fake=tmp_path/'docker.exe'
    fake.write_text("#!/usr/bin/env python3\nimport subprocess,sys\na=sys.argv[1:]\nr=subprocess.run([sys.executable,'-c',a[4]],capture_output=True,text=True,timeout=5)\nprint(r.stdout,end='');sys.exit(r.returncode)\n");fake.chmod(0o700)
    try:
        invoke=functions()+"""
$d=(Get-Command Test-DiagReady).Definition
$d=$d.Replace('http://TARGET:20241/ready',FIXTURE)
Set-Item function:Test-DiagReady -Value ([scriptblock]::Create($d))
$docker=DOCKER
$s=[pscustomobject]@{probe='fixture-probe';tunnel='fcqd-11111111111141118111111111111111-tunnel'}
Write-Output ((Test-DiagReady $s)|ConvertTo-Json -Compress)
""".replace('FIXTURE',quote(f'http://127.0.0.1:{server.server_port}/ready')).replace('DOCKER',quote(fake))
        result=ps(tmp_path,invoke,timeout=10,env={'HTTP_PROXY':'http://127.0.0.1:1','HTTPS_PROXY':'http://127.0.0.1:1','NO_PROXY':''})
        assert result.returncode==0,result.stdout+result.stderr
        value=json.loads(result.stdout);assert value['http_status']==status and value['active_connections']==count and value['ready']==expected,value
        assert 'MUST_NOT_PRINT_CONNECTOR' not in result.stdout+result.stderr
    finally:server.shutdown();server.server_close();thread.join(timeout=3)
