"""Synthetic nonce probe, owned cleanup, and immutable retry contracts."""
import json
from pathlib import Path
import pytest
from test_club_host_one_shot import ROOT, PWSH, ps, quote

SCRIPT=ROOT/'deploy/docker/club-deployment-feasibility.ps1'
pytestmark=pytest.mark.skipif(not PWSH, reason='PowerShell runtime unavailable')


def functions():
    return """$ErrorActionPreference='Stop'
$t=$null;$e=$null
$a=[Management.Automation.Language.Parser]::ParseFile(SCRIPT,[ref]$t,[ref]$e)
if($e.Count){throw 'parser errors'}
# Inline entry point is & { ... }; load definitions without running entry point.
$defs=$a.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$true)
foreach($f in $defs){. ([scriptblock]::Create($f.Extent.Text))}
""".replace('SCRIPT',quote(SCRIPT))


def test_tunnel_url_accepts_only_quick_tunnel_origin(tmp_path):
    assert SCRIPT.exists()
    result=ps(tmp_path,functions()+"""
$good=Get-ProbeUrl 'INFO https://sample-good.trycloudflare.com connected'
$bad=Get-ProbeUrl 'https://sample.trycloudflare.com.attacker.example https://bad.trycloudflare.com/path'
if($good -cne 'https://sample-good.trycloudflare.com' -or $bad){throw 'URL guard'}
Write-Output 'PASS'
""")
    assert result.returncode==0,result.stdout+result.stderr


def test_cleanup_refuses_foreign_label_and_no_global_delete(tmp_path):
    assert SCRIPT.exists()
    result=ps(tmp_path,functions()+"""
$script:calls=New-Object 'System.Collections.Generic.List[string]'
function Invoke-ProbeDocker([string[]]$Arguments,[int]$Limit=10){
 $script:calls.Add(($Arguments -join ' '))
 if($Arguments[0] -eq 'inspect'){return @{exit_code=0;stdout='FOREIGN';timed_out=$false}}
 return @{exit_code=0;stdout='';timed_out=$false}
}
$s=[pscustomobject]@{run_id='11111111-1111-4111-8111-111111111111';probe='fcp-probe';tunnel='fcp-tunnel';network='fcp-network'}
$ok=Remove-ProbeResources $s
if($ok -or @($script:calls|Where-Object {$_ -match '^(rm|network rm) '}).Count){throw 'foreign removal'}
Write-Output 'PASS'
""")
    assert result.returncode==0,result.stdout+result.stderr


def test_nonce_roundtrip_rejects_mismatch_and_builds_accurate_report(tmp_path):
    assert SCRIPT.exists()
    result=ps(tmp_path,functions()+"""
function Invoke-ToolHttp {return ,[Text.Encoding]::UTF8.GetBytes('{"nonce":"wrong"}')}
$x=Measure-ProbeHttps 'https://synthetic.trycloudflare.com' 'expected' 2
if($x.successes -ne 0 -or $x.attempts -ne 2){throw 'nonce accepted'}
Write-Output 'PASS'
""")
    assert result.returncode==0,result.stdout+result.stderr


def test_bounded_docker_preserves_stderr_for_tunnel_url_only(tmp_path):
    docker=tmp_path/'docker.exe'
    docker.write_text("#!/usr/bin/env python3\nimport sys\nprint('https://fixture-tunnel.trycloudflare.com',file=sys.stderr)\n")
    docker.chmod(0o700)
    result=ps(tmp_path,functions()+"""
function Stop-OwnedProcessTree($p){$p.Kill($true);return $p.WaitForExit(1000)}
$docker=DOCKER
$r=Invoke-ProbeDocker @('logs','--tail','80','fixture') 3
if($r.exit_code -ne 0 -or (Get-ProbeUrl ($r.stdout+"`n"+$r.stderr)) -cne 'https://fixture-tunnel.trycloudflare.com'){throw 'stderr missing'}
Write-Output 'PASS'
""".replace('DOCKER',quote(docker)))
    assert result.returncode==0,result.stdout+result.stderr


def test_synthetic_probe_success_cleanup_and_report_contract(tmp_path):
    from fucheng.deployment_report import REQUIRED_CHECKS
    host={'schema_version':1,'host':{'name':'synthetic-host','windows':'Windows synthetic','build':'fixture','install_drive_free_gib':100,'docker_platform':'linux/amd64','docker_server_version':'fixture'},'checks':[{'id':key,'status':'NOT_TESTED','reason':'Synthetic fixture.','evidence':'No native Windows operation.','next_action':'Validate at the club.'} for key in sorted(REQUIRED_CHECKS)]}
    hostfile=tmp_path/'host.json';hostfile.write_text(json.dumps(host))
    result=ps(tmp_path,functions()+"""
$appImage='app@sha256:fixture';$tunnelImage='tunnel@sha256:fixture';$docker='synthetic';$utf8=New-Object Text.UTF8Encoding($false)
$script:calls=New-Object 'System.Collections.Generic.List[object]'
function Invoke-ProbeDocker([string[]]$Arguments,[int]$Limit=10){
 $script:calls.Add(@($Arguments))
 if($Arguments[0] -eq 'inspect'){return @{exit_code=1;stdout='';stderr='';timed_out=$false}}
 $out=if($Arguments[0] -eq 'image'){'linux|amd64'}elseif($Arguments[0] -eq 'logs'){'INFO https://test-tunnel.trycloudflare.com connected'}else{''}
 return @{exit_code=0;stdout=$out;stderr='';timed_out=$false}
}
function Start-ProbeWatchdog {return $null}
function Invoke-ToolHttp([string]$Uri){
 if($Uri -like '*/cdn-cgi/trace'){return ,[Text.Encoding]::UTF8.GetBytes("ip=203.0.113.1`n")}
 return ,[Text.Encoding]::UTF8.GetBytes('{"nonce":"fixture"}')
}
$s=[pscustomobject]@{run_id='11111111-1111-4111-8111-111111111111';nonce='fixture';probe='fixture-probe';tunnel='fixture-tunnel';network='fixture-net'}
$p=Invoke-FeasibilityProbe $s DIRECTORY
$hostReport=[IO.File]::ReadAllText(HOSTFILE)|ConvertFrom-Json
$r=New-FeasibilityReport $hostReport $p
[IO.File]::WriteAllText(OUTFILE,($r|ConvertTo-Json -Depth 12))
[IO.File]::WriteAllText(CALLFILE,($script:calls|ConvertTo-Json -Depth 6))
""".replace('DIRECTORY',quote(tmp_path)).replace('HOSTFILE',quote(hostfile)).replace('OUTFILE',quote(tmp_path/'report.json')).replace('CALLFILE',quote(tmp_path/'calls.json')))
    assert result.returncode==0,result.stdout+result.stderr
    report=json.loads((tmp_path/'report.json').read_text())
    assert report['schema_version']==3 and report['report_type']=='deployment_feasibility'
    assert report['scope']=={'read_only_probes':False,'container_execution':True,'host_control':False,'live_volume_access':False,'temporary_public_probe':True,'external_network_opt_in':True}
    checks={c['id']:c for c in report['checks']}
    assert len(checks)==44 and set(REQUIRED_CHECKS)<set(checks)
    assert all(checks[key]['status']=='PASS' for key in ('isolated_probe','quick_tunnel','public_https_nonce','https_samples','temporary_cleanup'))
    assert checks['public_ingress']['status']=='NOT_TESTED'
    assert '203.0.113.1' not in json.dumps(report)
    calls=json.loads((tmp_path/'calls.json').read_text())
    runs=[args for args in calls if args[0]=='run']
    assert len(runs)==2 and all('--network' in args and '--platform' in args and '--restart' in args for args in runs)
    assert all(not(set(args)&{'-v','--volume','--mount','-p','--publish','--privileged','--network=host'}) for args in runs)
    assert '--protocol' in runs[1] and 'http2' in runs[1]
    # Receiver implementation is owned by the parent; validate it when present.
    from fucheng.deployment_report import parse_report
    parse_report(json.dumps(report).encode())


def test_cleanup_removes_only_inspected_ids(tmp_path):
    result=ps(tmp_path,functions()+"""
$script:calls=New-Object 'System.Collections.Generic.List[string]'
function Invoke-ProbeDocker([string[]]$Arguments,[int]$Limit=10){
 $script:calls.Add(($Arguments -join ' '))
 $out=if($Arguments[0] -eq 'inspect'){('a'*64)+'|11111111-1111-4111-8111-111111111111|nonce-only-v1'}else{''}
 return @{exit_code=0;stdout=$out;timed_out=$false}
}
$s=[pscustomobject]@{run_id='11111111-1111-4111-8111-111111111111';probe='fixture-probe';tunnel='fixture-tunnel';network='fixture-net'}
if(!(Remove-ProbeResources $s)){throw 'cleanup failed'}
$removed=@($script:calls|Where-Object {$_ -match '^(container rm|network rm) '})
if($removed.Count -ne 3 -or @($removed|Where-Object {$_ -notmatch ' a{64}$'}).Count){throw 'removal target'}
Write-Output 'PASS'
""")
    assert result.returncode==0,result.stdout+result.stderr


def test_import_verified_functions_retains_declared_parameters(tmp_path):
    result=ps(tmp_path,functions()+"""
Import-ProbeFunctions 'function Echo-Probe([string]$Name,[int]$Count=2){return $Name*$Count}' @('Echo-Probe')
if((Echo-Probe 'x' 3) -cne 'xxx'){throw 'function parameters lost'}
Write-Output 'PASS'
""")
    assert result.returncode==0,result.stdout+result.stderr


def test_host_health_uses_configured_host_header(tmp_path):
    result=ps(tmp_path,functions()+"""
$script:got=$null
function Invoke-ProbeDocker([string[]]$Arguments,[int]$Limit=10){
 if(($Arguments -join ' ') -like '*Config.Env*'){return @{exit_code=0;stdout='FUCHENG_PUBLIC_ORIGIN=https://club.example';timed_out=$false}}
 return @{exit_code=0;stdout='running|healthy|unless-stopped|0';timed_out=$false}
}
function Get-Command {return [pscustomobject]@{Source='fixture-curl'}}
function Invoke-Bounded($File,$Arguments,$Limit){$script:got=$Arguments;return @{exit_code=0;stdout='200';timed_out=$false}}
$c=Get-HostAwareHealth
if($c.status -cne 'PASS' -or $script:got -notlike '*Host: club.example*' -or $script:got -notlike '*127.0.0.1:8052/api/health*'){throw 'host header missing'}
Write-Output 'PASS'
""")
    assert result.returncode==0,result.stdout+result.stderr


def test_failed_probe_still_returns_report_and_cleanup_warning(tmp_path):
    result=ps(tmp_path,functions()+"""
$docker=$null
$s=[pscustomobject]@{run_id='11111111-1111-4111-8111-111111111111';nonce='fixture';probe='fixture-probe';tunnel='fixture-tunnel';network='fixture-net'}
$p=Invoke-FeasibilityProbe $s DIRECTORY
if($p.container_execution -or $p.temporary_public_probe -or $p.checks.probe_image.status -cne 'FAIL' -or $p.checks.temporary_cleanup.status -cne 'WARN'){throw 'failed probe not retained'}
Write-Output 'PASS'
""".replace('DIRECTORY',quote(tmp_path)))
    assert result.returncode==0,result.stdout+result.stderr


def test_inline_existing_unknown_report_and_cached_receipt_never_reprobe(tmp_path):
    import hashlib
    import zipfile
    from fucheng.deployment_report import FEASIBILITY_CHECKS
    run_id='11111111-1111-4111-8111-111111111111';short=run_id.replace('-','')
    workspace=tmp_path/'local data 繁中/FuchengDeploymentCheck';workspace.mkdir(parents=True)
    (workspace/'owner.txt').write_text('fucheng-deployment-feasibility-v1')
    directory=workspace/f'data/check-{short}';directory.mkdir(parents=True)
    old=tmp_path/'local data 繁中/FuchengClubHostCheck';old.mkdir();(old/'preserved.txt').write_text('original-report-untouched')
    state={'schema_version':1,'run_id':run_id,'nonce':'a'*32,'directory':f'data/check-{short}','probe':f'fcp-{short}-probe','tunnel':f'fcp-{short}-tunnel','network':f'fcp-{short}-net'}
    (workspace/'active-check.json').write_text(json.dumps(state))
    report={'schema_version':3,'report_type':'deployment_feasibility','checked_at':'2026-10-30T00:00:00Z','host':{'name':'synthetic','windows':'fixture','build':'fixture','install_drive_free_gib':100,'docker_platform':'linux/amd64','docker_server_version':'fixture'},'scope':{'read_only_probes':False,'container_execution':False,'host_control':False,'live_volume_access':False,'temporary_public_probe':False,'external_network_opt_in':True},'summary':{'PASS':0,'WARN':0,'FAIL':0,'NOT_TESTED':44},'checks':[{'id':key,'status':'NOT_TESTED','reason':'Synthetic.','evidence':'Synthetic.','next_action':'Validate Windows.'} for key in sorted(FEASIBILITY_CHECKS)],'recommendations':[{'candidate':'Synthetic','status':'NOT_TESTED','reason':'Synthetic.','next_action':'Validate Windows.'}],'sources':[]}
    raw=json.dumps(report).encode();(directory/'report.json').write_bytes(raw);(directory/'report.md').write_text('synthetic preserved')
    operation={'schema_version':1,'report_id':run_id,'endpoint':'https://momonong.me/fucheng/api/deployment-reports','device_id':'club-windows-01','raw_report_sha256':hashlib.sha256(raw).hexdigest()}
    opraw=json.dumps(operation).encode();(directory/'upload-operation.json').write_bytes(opraw)
    (directory/'upload-status.json').write_text(json.dumps({'report_id':run_id,'state':'unknown'}))
    payload={f'deploy/docker/{name}':(ROOT/'deploy/docker'/name).read_bytes() for name in ('host-preflight.ps1','send-host-report.ps1','club-host-network.ps1')}
    # The only fixture credential helper fails before any network operation.
    payload['deploy/docker/club-host-credential.ps1']=b"param($ReportDirectory,$ConfigFile)\nWrite-Host 'SYNTHETIC_CREDENTIAL_STOP';exit 2\n"
    payload['private/placeholder.txt']=b'synthetic nonsecret'
    payload['manifest.json']=json.dumps({'schema_version':1,'kind':'club-host-one-shot-kit','contains_credentials':False,'files':{key:hashlib.sha256(value).hexdigest() for key,value in payload.items()}}).encode()
    archive=tmp_path/'tools.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for key,value in payload.items():z.writestr(key,value)
    bootstrap=tmp_path/'bootstrap.ps1'
    bootstrap.write_text("function Invoke-ToolHttp {return ,[IO.File]::ReadAllBytes("+quote(archive)+")}\n"+(ROOT/'deploy/docker/club-host-bootstrap.ps1').read_text(encoding='utf-8-sig'),encoding='utf-8-sig')
    source=SCRIPT.read_text(encoding='utf-8-sig').replace('f54a5e9d21e6ef7affdb172823ebd3ff9d6f6783223227f184b99c39c3b1764f',hashlib.sha256(bootstrap.read_bytes()).hexdigest()).replace('3db404e85a53492a0eea347cc3f5409f5f238395d88eca12feb2aba0c5005956',hashlib.sha256(archive.read_bytes()).hexdigest())
    overrides="function Get-InitialTool {return ,[IO.File]::ReadAllBytes("+quote(bootstrap)+")}\nfunction Patch-ConsoleCredential([string]$Path){return $Path}\n"
    source=source.replace("$lock=$null;$tokenFile=$null;$stage='download';$directory=$null",overrides+"$lock=$null;$tokenFile=$null;$stage='download';$directory=$null")
    for _ in range(2):
        result=ps(tmp_path,source+'\nexit $LASTEXITCODE',timeout=25)
        assert result.returncode==2 and 'SYNTHETIC_CREDENTIAL_STOP' in result.stdout,result.stdout+result.stderr
        assert (directory/'report.json').read_bytes()==raw and (directory/'upload-operation.json').read_bytes()==opraw
    (directory/'upload-receipt.json').write_text(json.dumps({'report_id':run_id,'device_id':'club-windows-01','digest':'a'*64,'received_at':'2026-10-30T00:00:00Z'}))
    result=ps(tmp_path,source+'\nexit $LASTEXITCODE',timeout=25)
    assert result.returncode==0 and 'SYNTHETIC_CREDENTIAL_STOP' not in result.stdout,result.stdout+result.stderr
    assert (directory/'report.json').read_bytes()==raw and (directory/'upload-operation.json').read_bytes()==opraw
    assert (old/'preserved.txt').read_text()=='original-report-untouched'
    assert not list(workspace.rglob('report-upload-token.txt'))
    # Missing continuity metadata must never silently create a replacement UUID.
    (workspace/'active-check.json').unlink()
    fast_source='\n'.join('$result=2' if '$result=Invoke-BootstrapChild $native ' in line else line for line in source.splitlines())
    stopped=ps(tmp_path,fast_source+'\nexit $LASTEXITCODE',timeout=20)
    assert stopped.returncode==2 and not (workspace/'active-check.json').exists(),stopped.stdout+stopped.stderr
    (workspace/'active-check.json').write_text(json.dumps(state))
    (directory/'report.json').unlink()
    stopped=ps(tmp_path,fast_source+'\nexit $LASTEXITCODE',timeout=20)
    assert stopped.returncode==2 and 'stage=tools' in stopped.stdout,stopped.stdout+stopped.stderr
    assert not (directory/'report.json').exists() and (directory/'upload-operation.json').read_bytes()==opraw


@pytest.mark.parametrize('mode',['nonce','mismatch','redirect'])
def test_real_tls_nonce_read_and_redirect_rejection(tmp_path,mode):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import ssl
    import subprocess
    from threading import Thread
    paths=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            paths.append(self.path)
            if mode=='redirect':
                self.send_response(302);self.send_header('Location','/must-not-follow');self.send_header('Content-Length','0');self.end_headers();return
            body=json.dumps({'nonce':'fixture' if mode=='nonce' else 'wrong'}).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    cert=tmp_path/'cert.pem';key=tmp_path/'key.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],check=True,capture_output=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(cert,key);server.socket=tls.wrap_socket(server.socket,server_side=True)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    network=(ROOT/'deploy/docker/club-host-network.ps1').read_text(encoding='utf-8-sig').replace('function Invoke-ToolHttp(','function Invoke-FixtureHttp(',1)
    try:
        result=ps(tmp_path,functions()+network+"""
function Invoke-ToolHttp([string]$Uri,[string]$Method,[byte[]]$Body,$Cookies,[string]$Csrf,[int]$MaxBytes,[int]$TimeoutSeconds){
 return ,(Invoke-FixtureHttp ($Uri.Replace('https://fixture.trycloudflare.com',ORIGIN)) $Method $Body $Cookies $Csrf $MaxBytes $TimeoutSeconds)
}
$x=Measure-ProbeHttps 'https://fixture.trycloudflare.com' 'fixture' 1
Write-Output ('SUCCESSES='+$x.successes)
""".replace('ORIGIN',quote(f'https://localhost:{server.server_port}')),env={'SSL_CERT_FILE':str(cert)})
        assert result.returncode==0 and f'SUCCESSES={int(mode=="nonce")}' in result.stdout,result.stdout+result.stderr
        assert paths==['/probe/fixture']
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)


def test_native_arguments_preserve_python_source_and_spaces(tmp_path):
    docker=tmp_path/'docker.exe'
    docker.write_text("#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n");docker.chmod(0o700)
    values=['run','two words','import base64;exec("nonce")','C:\\trailing\\','', '繁體中文']
    args=','.join(quote(value) for value in values)
    result=ps(tmp_path,functions()+f"$docker={quote(docker)}\n$r=Invoke-ProbeDocker @({args}) 3\nWrite-Output $r.stdout\n")
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout.strip())==values


def test_independent_watchdog_runs_label_checked_cleanup(tmp_path):
    docker=tmp_path/'docker.exe';calls=tmp_path/'watchdog-calls.jsonl'
    docker.write_text("#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\nargs=sys.argv[1:]\nwith Path("+repr(str(calls))+").open('a') as f:f.write(json.dumps(args)+'\\n')\nif args[0]=='inspect':print('a'*64+'|11111111-1111-4111-8111-111111111111|nonce-only-v1')\n")
    docker.chmod(0o700)
    result=ps(tmp_path,functions()+"""
$native=[IO.File]::ReadAllText(PREFLIGHT).TrimStart([char]0xFEFF)
Import-ProbeFunctions $native @('Stop-OwnedProcessTree','Invoke-Bounded')
$docker=DOCKER
# Accelerate only the test deadline; the production child remains at 600 seconds.
$body=(Get-Command Start-ProbeWatchdog).Definition.Replace('Start-Sleep -Seconds 600','Start-Sleep -Seconds 1')
Set-Item function:Start-ProbeWatchdog -Value ([scriptblock]::Create($body))
$s=[pscustomobject]@{run_id='11111111-1111-4111-8111-111111111111';nonce='fixture';probe='fixture-probe';tunnel='fixture-tunnel';network='fixture-net'}
$p=Start-ProbeWatchdog $s DIRECTORY
try{if(!$p.WaitForExit(10000) -or $p.ExitCode -ne 0){throw 'watchdog timeout'}}finally{if(!$p.HasExited){$p.Kill($true)};$p.Dispose()}
Write-Output 'PASS'
""".replace('PREFLIGHT',quote(ROOT/'deploy/docker/host-preflight.ps1')).replace('DOCKER',quote(docker)).replace('DIRECTORY',quote(tmp_path)),timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
    rows=[json.loads(line) for line in calls.read_text().splitlines()]
    removed=[args for args in rows if args[1]=='rm']
    assert len(removed)==3 and all(args[-1]=='a'*64 for args in removed)


def test_console_inline_prints_complete_results_without_auth_or_reprobe(tmp_path):
    import hashlib
    import zipfile
    from fucheng.deployment_report import REQUIRED_CHECKS
    console=ROOT/'deploy/docker/club-deployment-feasibility-console.ps1'
    assert console.exists()
    host={'schema_version':1,'host':{'name':'synthetic','windows':'fixture','build':'fixture','install_drive_free_gib':100,'docker_platform':'linux/amd64','docker_server_version':'fixture'},'checks':[{'id':key,'status':'NOT_TESTED','reason':'Synthetic.','evidence':'fixture evidence','next_action':'Synthetic next.'} for key in sorted(REQUIRED_CHECKS)]}
    preflight="param($OutputDir,$InstallPath,$ContainerName,$TestPort,$ImageRef,$TimeoutSeconds,$ProbeNetwork)\n[void][IO.Directory]::CreateDirectory($OutputDir)\n[IO.File]::WriteAllText((Join-Path $OutputDir 'report.json'),"+quote(json.dumps(host))+")\n[IO.File]::WriteAllText((Join-Path $OutputDir 'report.md'),'synthetic readonly host report')\nexit 0\n"
    # Real bounded process helpers are extracted from the trusted preflight function definitions.
    helper_source=(ROOT/'deploy/docker/host-preflight.ps1').read_text(encoding='utf-8-sig')
    start=helper_source.index('function Stop-OwnedProcessTree(');end=helper_source.index('\nfunction ',helper_source.index('function Invoke-Bounded(')+10)
    preflight+=helper_source[start:end]
    payload={'deploy/docker/host-preflight.ps1':preflight.encode('utf-8-sig'),'private/placeholder.txt':b'nonsecret'}
    payload['manifest.json']=json.dumps({'schema_version':1,'kind':'club-host-one-shot-kit','contains_credentials':False,'files':{key:hashlib.sha256(value).hexdigest() for key,value in payload.items()}}).encode()
    archive=tmp_path/'console-tools.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for key,value in payload.items():z.writestr(key,value)
    bootstrap=tmp_path/'console-bootstrap.ps1'
    network="function Invoke-ToolHttp([string]$Uri){if($Uri -like '*/tools.zip'){return ,[IO.File]::ReadAllBytes("+quote(archive)+")};if($Uri -like '*/cdn-cgi/trace'){return ,[Text.Encoding]::UTF8.GetBytes(\"ip=203.0.113.1`n\")};throw 'UNEXPECTED_NETWORK'}\n"
    bootstrap.write_text(network+(ROOT/'deploy/docker/club-host-bootstrap.ps1').read_text(encoding='utf-8-sig'),encoding='utf-8-sig')
    source=console.read_text(encoding='utf-8-sig')
    assert not any(value in source for value in ('Get-Credential','Read-Host','PSCredential','/auth/','report-upload-token','upload-operation','/deployment-reports','Patch-ConsoleCredential',"'POST'"))
    source=source.replace('f54a5e9d21e6ef7affdb172823ebd3ff9d6f6783223227f184b99c39c3b1764f',hashlib.sha256(bootstrap.read_bytes()).hexdigest()).replace('3db404e85a53492a0eea347cc3f5409f5f238395d88eca12feb2aba0c5005956',hashlib.sha256(archive.read_bytes()).hexdigest())
    counter=tmp_path/'console-probe-count.txt';downloads=tmp_path/'console-download-count.txt'
    overrides="function Get-InitialTool {[IO.File]::AppendAllText("+quote(downloads)+",'download\\n');return ,[IO.File]::ReadAllBytes("+quote(bootstrap)+")}\n"
    overrides+="""function Invoke-FeasibilityProbe($State,[string]$Directory){
[IO.File]::AppendAllText(COUNTER,'probe\n');$c=@{}
foreach($key in @('probe_image','isolated_probe','quick_tunnel','public_https_nonce','https_samples','temporary_cleanup')){Set-FeasibilityCheck $c $key 'NOT_TESTED' 'Synthetic.' 'fixture evidence' 'Synthetic next.'}
return @{checks=$c;container_execution=$false;temporary_public_probe=$false;cleanup=$true}
}
""".replace('COUNTER',quote(counter))
    source=source.replace("$lock=$null;$stage=",overrides+"$lock=$null;$stage=",1)
    for folder in ('FuchengClubHostCheck','FuchengDeploymentCheck'):
        directory=tmp_path/'local data 繁中'/folder;directory.mkdir(parents=True);(directory/'preserved.txt').write_text('original')
    first=ps(tmp_path,source+'\nexit $LASTEXITCODE',timeout=25)
    assert first.returncode==0,first.stdout+first.stderr
    workspace=tmp_path/'local data 繁中/FuchengDeploymentCheckConsole'
    directory=workspace/json.loads((workspace/'active-check.json').read_text())['directory']
    raw=(directory/'report.json').read_bytes();markdown=(directory/'report.md').read_text(encoding='utf-8-sig')
    assert len(json.loads(raw)['checks'])==44
    assert first.stdout.count('=== 府城部署檢查結果開始 ===')==first.stdout.count('=== 府城部署檢查結果結束 ===')==1
    assert markdown in first.stdout and markdown.count('- 原因：')==44 and markdown.count('- 證據：')==44 and markdown.count('- 下一步：')==44
    assert 'NOT_TESTED' in markdown and 'static_ip_contract' in markdown and 'isp_inbound_policy' in markdown
    cached=ps(tmp_path,source+'\nexit $LASTEXITCODE',timeout=15)
    assert cached.returncode==0 and markdown in cached.stdout,cached.stdout+cached.stderr
    assert (directory/'report.json').read_bytes()==raw and counter.read_text()=='probe\n' and downloads.read_text()=='download\\n'
    assert not list(workspace.rglob('*token*')) and not list(workspace.rglob('upload-*'))
    for folder in ('FuchengClubHostCheck','FuchengDeploymentCheck'):
        assert (tmp_path/'local data 繁中'/folder/'preserved.txt').read_text()=='original'
