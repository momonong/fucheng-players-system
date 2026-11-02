"""Synthetic PowerShell contracts; Windows 5.1 and native probes remain untested."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from fucheng.deployment_report import REQUIRED_CHECKS, HostReport

ROOT = Path(__file__).resolve().parents[1]
PWSH = os.environ.get('FUCHENG_TEST_PWSH') or shutil.which('pwsh')
pytestmark = pytest.mark.skipif(not PWSH, reason='PowerShell runtime unavailable')


def ps(tmp_path, source, *, timeout=20, env=None):
    (tmp_path/'local data 繁中').mkdir(exist_ok=True)
    path = tmp_path/'invoke.ps1'
    path.write_text(source, encoding='utf-8-sig')
    return subprocess.run([str(PWSH), '-NoProfile', '-NonInteractive', '-File', str(path)],
        text=True, capture_output=True, timeout=timeout,
        env=os.environ | {'POWERSHELL_TELEMETRY_OPTOUT':'1', 'POWERSHELL_UPDATECHECK':'Off',
            'COMPUTERNAME':'synthetic-host', 'XDG_DATA_HOME':str(tmp_path/'local data 繁中'), **(env or {})})


def quote(path):
    return "'" + str(path).replace("'", "''") + "'"


def preflight(tmp_path, *, state='running|unhealthy|unless-stopped|2', native_commands=False):
    kit = tmp_path/'kit'
    scripts = kit/'deploy/docker'
    scripts.mkdir(parents=True)
    shutil.copyfile(ROOT/'deploy/docker/host-preflight.ps1', scripts/'host-preflight.ps1')
    docker = tmp_path/'docker.exe'
    docker.write_text('''#!/usr/bin/env python3
import json,sys
from pathlib import Path
args=sys.argv[1:]
with Path(__file__).with_suffix('.calls').open('a') as log: log.write(json.dumps(args)+'\\n')
if args[0]=='info': print('linux|x86_64|28.5.1')
elif args[:2]==['compose','version']: print('5.6.0')
elif args[:2]==['image','inspect']: print('linux|amd64')
elif args[:2]==['network','ls']: pass
elif args[0]=='inspect': print(STATE)
else: sys.exit(1)
'''.replace('STATE', repr(state)))
    docker.chmod(0o700)
    if native_commands:
        for name, content in {
            'powercfg.exe':"print('AC 0x00000000\\nDC 0x00000001')",
            'curl.exe':"print('200')",
        }.items():
            native = tmp_path/name
            native.write_text('#!/usr/bin/env python3\n'+content+'\n')
            native.chmod(0o700)
    output = kit/'data/report'
    result = ps(tmp_path, '''function Get-CimInstance {
param($ClassName,$OperationTimeoutSec,$Filter)
switch ($ClassName) {
'Win32_OperatingSystem' { [pscustomobject]@{Caption='Windows 11 Pro';BuildNumber='26200'} }
'Win32_ComputerSystem' { [pscustomobject]@{TotalPhysicalMemory=16GB;HypervisorPresent=$false} }
'Win32_Processor' { throw 'synthetic CPU denied' }
default { throw 'synthetic unavailable' }
}
}
& SCRIPT -OutputDir OUTPUT -DockerExecutable DOCKER -ContainerName fucheng-check-v120 -TimeoutSeconds 1
'''.replace('SCRIPT', quote(scripts/'host-preflight.ps1')).replace('OUTPUT', quote(output)).replace('DOCKER', quote(docker)),env={'PATH':str(tmp_path)+os.pathsep+os.environ['PATH']})
    return result, output, docker.with_suffix('.calls')


def test_cpu_failure_keeps_exactly_35_unique_checks_and_named_container(tmp_path):
    result, output, calls = preflight(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads((output/'report.json').read_text())
    HostReport.model_validate_json((output/'report.json').read_text())
    assert len(payload['checks']) == len({c['id'] for c in payload['checks']}) == 35
    assert {c['id'] for c in payload['checks']} == REQUIRED_CHECKS
    checks = {c['id']:c for c in payload['checks']}
    assert checks['memory']['status'] == 'PASS'
    assert checks['virtualization']['status'] == 'NOT_TESTED'
    assert checks['project_health']['status'] == 'WARN'
    assert 'unhealthy' in checks['project_health']['evidence']
    arguments = [json.loads(line) for line in calls.read_text().splitlines()]
    inspect = [a for a in arguments if a[0] == 'inspect']
    assert len(inspect) == 1 and inspect[0][-1] == 'fucheng-check-v120'
    assert not any(a[0] in ('ps','run','restart','exec') for a in arguments)


@pytest.mark.parametrize('state', ['running|none|no|0','exited|unhealthy|always|3'])
def test_running_without_health_or_restart_is_not_pass(tmp_path, state):
    result, output, _ = preflight(tmp_path,state=state)
    assert result.returncode == 0, result.stdout + result.stderr
    check = next(c for c in json.loads((output/'report.json').read_text())['checks'] if c['id']=='project_health')
    assert check['status'] != 'PASS'


def test_readonly_hibernate_and_local_health_do_not_claim_https_or_boot(tmp_path):
    result, output, _ = preflight(tmp_path,state='running|healthy|unless-stopped|0',native_commands=True)
    assert result.returncode == 0, result.stdout+result.stderr
    payload = json.loads((output/'report.json').read_text())
    checks = {c['id']:c for c in payload['checks']}
    assert checks['project_health']['status']=='PASS'
    assert 'local_http=200' in checks['project_health']['evidence']
    assert checks['ac_sleep']['status']==checks['hibernate_policy']['status']=='PASS'
    assert 'powercfg_ac_hibernate_seconds=0' in checks['hibernate_policy']['evidence']
    assert checks['preview_https']['status']==checks['cold_boot_recovery']['status']=='NOT_TESTED'
    assert checks['domain_dns']['status']==checks['docker_data_root']['status']=='NOT_TESTED'


def test_bounded_process_does_not_wait_for_descendants_inheriting_pipes(tmp_path):
    executable = tmp_path/'pipe-owner'
    executable.write_text('#!/usr/bin/env python3\nimport subprocess\nsubprocess.Popen(["sleep","8"])\n')
    executable.chmod(0o700)
    source = '''$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile(SCRIPT,[ref]$tokens,[ref]$errors)
$f=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Invoke-Bounded'},$true)
. ([scriptblock]::Create($f.Extent.Text))
$r=Invoke-Bounded EXECUTABLE '' 1
$r | ConvertTo-Json -Compress
'''.replace('SCRIPT', quote(ROOT/'deploy/docker/host-preflight.ps1')).replace('EXECUTABLE', quote(executable))
    started = time.monotonic()
    try:
        result = ps(tmp_path, source, timeout=5)
    except subprocess.TimeoutExpired:
        pytest.fail('process drain exceeded its bound after the parent exited')
    assert time.monotonic()-started < 4.5
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['timed_out'] is True


def runner_kit(tmp_path, endpoint='https://localhost:443/api/deployment-reports', *, token=True, preflight_mode='normal'):
    from test_deployment_report import report
    from test_device_reports import TOKEN
    kit = tmp_path/'ready folder 繁中'
    scripts = kit/'deploy/docker'
    scripts.mkdir(parents=True, exist_ok=True)
    for name in ('club-host-one-shot.ps1','send-host-report.ps1'):
        shutil.copyfile(ROOT/'deploy/docker'/name, scripts/name)
    payload = report()
    payload['checks'][0]['status'] = 'FAIL'
    payload['summary']['FAIL'] = 1
    payload['summary']['PASS'] -= 1
    fixture = base64.b64encode(json.dumps(payload).encode()).decode()
    (scripts/'host-preflight.ps1').write_text('''param($OutputDir,$InstallPath,$ContainerName,$TestPort,$ImageRef,$TimeoutSeconds,[switch]$ProbeNetwork)
$ErrorActionPreference='Stop'
if ($ContainerName -ne 'fucheng-check-v120' -or $TestPort -ne 8052 -or $ImageRef -notmatch '@sha256:0e5a297b') { throw 'wrong invocation' }
MODE
New-Item -ItemType Directory -Path $OutputDir | Out-Null
[IO.File]::WriteAllBytes((Join-Path $OutputDir 'report.json'),[Convert]::FromBase64String('FIXTURE'))
[IO.File]::WriteAllText((Join-Path $OutputDir 'report.md'),'synthetic Windows fixture')
'''.replace('FIXTURE',fixture).replace('MODE', {'normal':'','fail':"throw 'never-print-secret-failure'",'hang':'Start-Sleep -Seconds 30','slow':'Start-Sleep -Seconds 11'}[preflight_mode]),encoding='utf-8-sig')
    private = kit/'private'
    private.mkdir(exist_ok=True)
    (private/'club-report.json').write_text(json.dumps({'endpoint':endpoint,'device_id':'club-synthetic-01','token_file':'token.txt'}))
    if token: (private/'token.txt').write_text(TOKEN)
    return kit


def run_runner(tmp_path, kit, *, cert=None, new=False, deadline=30):
    source = '& SCRIPT -DeadlineSeconds DEADLINE NEW\nexit $LASTEXITCODE\n'.replace('SCRIPT',quote(kit/'deploy/docker/club-host-one-shot.ps1')).replace('DEADLINE',str(deadline)).replace('NEW','-NewCheck' if new else '')
    result = ps(tmp_path,source,timeout=deadline+10,env={'SSL_CERT_FILE':str(cert)} if cert else {})
    from test_device_reports import TOKEN
    assert TOKEN not in result.stdout+result.stderr
    assert 'never-print-' not in result.stdout+result.stderr
    workspace = tmp_path/'local data 繁中/FuchengClubHostCheck'
    return result, workspace


def test_runner_missing_token_preserves_report_and_retry_not_new_check(tmp_path):
    kit = runner_kit(tmp_path,token=False)
    first,workspace = run_runner(tmp_path,kit)
    assert first.returncode == 2, first.stdout+first.stderr
    active = json.loads((workspace/'active-report.json').read_text())['directory']
    directory = workspace/active
    original = (directory/'report.json').read_bytes()
    assert (directory/'report.md').exists()
    second,_ = run_runner(tmp_path,kit)
    assert second.returncode == 2
    assert (directory/'report.json').read_bytes() == original
    assert len(list((workspace/'data').glob('host-*'))) == 1
    # Explicit new check cannot abandon an unreceived report.
    again,_ = run_runner(tmp_path,kit,new=True)
    assert again.returncode == 2
    assert len(list((workspace/'data').glob('host-*'))) == 1


@pytest.mark.parametrize('mode,deadline', [('fail',30),('hang',3)])
def test_runner_preflight_error_or_deadline_is_actionable_and_safe(tmp_path,mode,deadline):
    kit = runner_kit(tmp_path,preflight_mode=mode)
    start = time.monotonic()
    result,workspace = run_runner(tmp_path,kit,deadline=deadline)
    assert result.returncode == (5 if mode=='hang' else 2), result.stdout+result.stderr
    assert (workspace/'active-report.json').exists()
    assert time.monotonic()-start < deadline+6
    assert not list(workspace.rglob('upload-receipt.json'))
    assert not list(workspace.rglob('upload-operation.json'))


def test_runner_real_sender_unknown_retry_receipt_and_explicit_new(tmp_path,app):
    from test_host_report_sender import tls_receiver
    with tls_receiver(tmp_path,app,'drop_once') as (endpoint,cert,attempts):
        kit = runner_kit(tmp_path,endpoint)
        original_token_mode = (kit/'private/token.txt').stat().st_mode
        first,workspace = run_runner(tmp_path,kit,cert=cert)
        assert first.returncode == 4, first.stdout+first.stderr
        assert (kit/'private/token.txt').stat().st_mode == original_token_mode
        assert (workspace/'private/report-upload-token.txt').stat().st_mode & 0o077 == 0
        assert (workspace/'private/club-report.json').stat().st_mode & 0o077 == 0
        report_path = workspace/json.loads((workspace/'active-report.json').read_text())['directory']
        operation = (report_path/'upload-operation.json').read_bytes()
        payload = (report_path/'report.json').read_bytes()
        # Restoring response retries exact original body/UUID; FAIL checks are sent.
        retry,_ = run_runner(tmp_path,kit,cert=cert)
        assert retry.returncode == 0, retry.stdout+retry.stderr
        assert (report_path/'upload-operation.json').read_bytes() == operation
        assert (report_path/'report.json').read_bytes() == payload
        assert len(attempts)==2 and attempts[0]['body']==attempts[1]['body']
        cached,_ = run_runner(tmp_path,kit,cert=cert)
        assert cached.returncode == 0 and len(attempts)==2
        new,_ = run_runner(tmp_path,kit,cert=cert,new=True)
        assert new.returncode == 0 and len(attempts)==3
        assert attempts[0]['path'] != attempts[2]['path']
        assert any(c['status']=='FAIL' for c in json.loads(attempts[0]['body'])['checks'])
        # A corrupt receipt cannot authorize leaving the prior operation.
        new_path = workspace/json.loads((workspace/'active-report.json').read_text())['directory']
        original_active = (workspace/'active-report.json').read_bytes()
        (new_path/'upload-receipt.json').write_text('{"report_id":"not-a-receipt"}')
        invalid,_ = run_runner(tmp_path,kit,cert=cert,new=True)
        assert invalid.returncode == 2 and len(attempts)==3
        assert (workspace/'active-report.json').read_bytes() == original_active


@pytest.mark.parametrize('missing', ['token','config'])
def test_new_check_with_explicit_missing_token_cannot_use_preserved_old_credential(tmp_path,app,missing):
    from test_host_report_sender import tls_receiver
    with tls_receiver(tmp_path,app) as (endpoint,cert,attempts):
        kit = runner_kit(tmp_path,endpoint)
        first,workspace = run_runner(tmp_path,kit,cert=cert)
        assert first.returncode==0 and len(attempts)==1
        preserved = (workspace/'private/report-upload-token.txt').read_bytes()
        if missing=='token':
            (kit/'private/token.txt').rename(kit/'private/token-kept.txt')
        else:
            (kit/'private/club-report.json').rename(kit/'private/config-kept.json')
        missing,_ = run_runner(tmp_path,kit,cert=cert,new=True)
        assert missing.returncode==2 and len(attempts)==1
        assert (workspace/'private/report-upload-token.txt').read_bytes()==preserved
        report_path = workspace/json.loads((workspace/'active-report.json').read_text())['directory']
        operation = (report_path/'upload-operation.json').read_bytes()
        assert (report_path/'report.json').exists()
        # Removing the source config cannot silently reactivate the old token.
        if (kit/'private/club-report.json').exists():
            (kit/'private/club-report.json').rename(kit/'private/config-kept.json')
        retry,_ = run_runner(tmp_path,kit,cert=cert)
        assert retry.returncode==2 and len(attempts)==1
        assert (report_path/'upload-operation.json').read_bytes()==operation


def test_runner_progress_is_visible_while_waiting_for_child_result(tmp_path):
    kit = runner_kit(tmp_path,token=False,preflight_mode='slow')
    result,workspace = run_runner(tmp_path,kit)
    assert result.returncode == 2, result.stdout+result.stderr
    assert '仍在健檢' in result.stdout
    assert list(workspace.rglob('report.json'))


def test_runner_refuses_existing_unowned_workspace_without_changing_it(tmp_path):
    kit = runner_kit(tmp_path)
    workspace = tmp_path/'local data 繁中/FuchengClubHostCheck'
    workspace.mkdir(parents=True)
    unrelated = workspace/'keep.txt'
    unrelated.write_text('preserve unrelated work')
    mode = workspace.stat().st_mode
    result,_ = run_runner(tmp_path,kit)
    assert result.returncode == 2
    assert unrelated.read_text()=='preserve unrelated work' and workspace.stat().st_mode==mode
    assert set(workspace.iterdir())=={unrelated}


def test_one_shot_package_allowlist_manifest_and_credentials_exclusion(tmp_path):
    import hashlib
    import importlib.util
    import zipfile
    from test_device_reports import TOKEN
    spec = importlib.util.spec_from_file_location('one_shot_package',ROOT/'scripts/club_host_one_shot_package.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = tmp_path
    for source in module.FILES:
        destination = tmp_path/source
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes((ROOT/source).read_bytes())
    private = tmp_path/'private/token.txt'
    private.parent.mkdir(exist_ok=True)
    private.write_text(TOKEN)
    result = module.create_package(tmp_path/'data/package.zip')
    with zipfile.ZipFile(result['archive']) as archive:
        assert set(archive.namelist()) == set(module.FILES.values()) | {'manifest.json'}
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['contains_credentials'] is False and manifest['source_kind']=='working-tree snapshot'
        for name,digest in manifest['files'].items():
            content = archive.read(name)
            assert hashlib.sha256(content).hexdigest()==digest and TOKEN.encode() not in content
            if name.endswith('.ps1'): assert content.startswith(b'\xef\xbb\xbf')
    with pytest.raises(FileExistsError): module.create_package(Path(result['archive']))
    with pytest.raises(ValueError): module.create_package(tmp_path/'outside.zip')


def process_is_running(pid):
    # Linux PowerShell harness: a reaped or zombie process cannot keep querying.
    status = Path(f'/proc/{pid}/stat')
    if not status.exists(): return False
    return status.read_text().split(') ',1)[1][0] != 'Z'


def test_preflight_timeout_stops_only_its_owned_process_tree(tmp_path):
    executable = tmp_path/'owned-tree'
    child_pid = tmp_path/'owned-child.pid'
    executable.write_text('''#!/usr/bin/env python3
import subprocess,time
from pathlib import Path
child=subprocess.Popen(['sleep','30'])
Path(PIDFILE).write_text(str(child.pid))
time.sleep(30)
'''.replace('PIDFILE',repr(str(child_pid))))
    executable.chmod(0o700)
    source = '''$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile(SCRIPT,[ref]$tokens,[ref]$errors)
foreach ($name in @('Stop-OwnedProcessTree','Invoke-Bounded')) {
$f=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true)
. ([scriptblock]::Create($f.Extent.Text))
}
Invoke-Bounded EXECUTABLE '' 1 | ConvertTo-Json -Compress
'''.replace('SCRIPT',quote(ROOT/'deploy/docker/host-preflight.ps1')).replace('EXECUTABLE',quote(executable))
    unrelated = subprocess.Popen(['sleep','30'])
    try:
        result = ps(tmp_path,source,timeout=6)
        assert result.returncode==0, result.stdout+result.stderr
        parsed = json.loads(result.stdout)
        assert parsed['timed_out'] and parsed['cleanup_confirmed']
        assert not process_is_running(int(child_pid.read_text()))
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=3)


def test_runner_deadline_stops_owned_child_queries_but_keeps_other_process(tmp_path):
    kit = runner_kit(tmp_path)
    child_pid = tmp_path/'child-query.pid'
    command = '$p=Start-Process -FilePath /bin/sleep -ArgumentList 30 -PassThru; [IO.File]::WriteAllText(PIDFILE,[string]$p.Id); Start-Sleep 30'.replace('PIDFILE',quote(child_pid))
    (kit/'deploy/docker/host-preflight.ps1').write_text('param($OutputDir,$InstallPath,$ContainerName,$TestPort,$ImageRef,$TimeoutSeconds,[switch]$ProbeNetwork)\n'+command,encoding='utf-8-sig')
    unrelated = subprocess.Popen(['sleep','30'])
    try:
        result,_ = run_runner(tmp_path,kit,deadline=3)
        assert result.returncode==5, result.stdout+result.stderr
        assert child_pid.exists() and not process_is_running(int(child_pid.read_text()))
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=3)


def test_pasted_launcher_preserves_shell_preference_and_passes_spaced_path(tmp_path):
    desktop = tmp_path/'desktop folder 繁中'
    ready = desktop/'fucheng-check-v120-ready'
    ready.mkdir(parents=True)
    (ready/'RUN-CHECK.cmd').write_text('synthetic launcher entry')
    scripts = ready/'deploy/docker'
    scripts.mkdir(parents=True)
    (scripts/'club-host-one-shot.ps1').write_text('# synthetic destination, intercepted below')
    # Linux has no Windows desktop API; substitute only that native directory.
    launcher = tmp_path/'launcher-fixture.ps1'
    launcher.write_text((ROOT/'deploy/docker/launch-club-host-check.ps1').read_text(encoding='utf-8-sig').replace("[Environment]::GetFolderPath('Desktop')",quote(desktop)),encoding='utf-8-sig')
    result = ps(tmp_path,'''$ErrorActionPreference='Continue'
$global:called=$false
function powershell.exe {
    param([Parameter(ValueFromRemainingArguments=$true)]$Options)
    $global:called=$true
    if (@($Options)[-1] -cne EXPECTED) { throw 'wrong path handoff' }
}
Invoke-Expression ([IO.File]::ReadAllText(SCRIPT))
if ($ErrorActionPreference -ne 'Continue' -or !$global:called) { throw 'launcher scope/dispatch broken' }
Write-Output 'launcher-scope-ok'
'''.replace('EXPECTED',quote(scripts/'club-host-one-shot.ps1')).replace('SCRIPT',quote(launcher)))
    assert result.returncode==0 and 'launcher-scope-ok' in result.stdout, result.stdout+result.stderr
    assert '尚未啟動' not in result.stdout
