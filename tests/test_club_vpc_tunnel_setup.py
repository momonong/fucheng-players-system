"""Connector-only inline setup contracts; Windows ACL / Docker Desktop remain live QA."""
import base64
import json

import pytest
from test_club_host_one_shot import ROOT, PWSH, ps, quote

SCRIPT = ROOT / 'deploy/docker/club-vpc-tunnel-setup.ps1'
pytestmark = pytest.mark.skipif(not PWSH, reason='PowerShell runtime unavailable')
TUNNEL = 'fa458cdb-0bf4-43a2-89ef-e9d15b348d14'
TOKEN = base64.b64encode(json.dumps({'a': 'fixture-account', 't': TUNNEL, 's': 'SECRET_SENTINEL'}).encode()).decode()


def invoke(tmp_path, *, token=TOKEN, mode='clean', env=None):
    source = SCRIPT.read_text(encoding='utf-8-sig')
    calls = tmp_path / 'calls.json'
    overrides = r'''
function Assert-VpcWindows {}
function Set-VpcPrivatePath([string]$Path,[bool]$Directory) {}
function Assert-VpcOwner([string]$Path) {}
function Get-Command([string]$Name){return [pscustomobject]@{Source='fixture-docker.exe'}}
function Read-Host {param($Prompt,[switch]$AsSecureString) $script:reads++;return (ConvertTo-SecureString TOKEN -AsPlainText -Force)}
function Start-Sleep {}
$script:calls=New-Object 'System.Collections.Generic.List[object]';$script:reads=0
function Invoke-ProbeDocker([string[]]$Arguments,[int]$Limit=10){
 $script:calls.Add(@($Arguments));$out='';$code=0
 if($Arguments[0] -eq 'context'){$out=if(MODE -eq 'remote_pipe'){'npipe:////other-host/pipe/docker_engine'}else{'npipe:////./pipe/dockerDesktopLinuxEngine'}}
 elseif($Arguments[0] -eq 'info'){$out='linux|x86_64'}
 elseif($Arguments[0] -eq 'image'){$out='linux|amd64';if(MODE -eq 'missing_image'){$code=1}}
 elseif($Arguments[0] -eq 'logs'){$out='Registered tunnel connection connIndex=0 protocol=quic SECRET_RAW_LOG'}
 elseif($Arguments[0] -eq 'inspect'){$out='running'}
 elseif(($Arguments -join ' ') -like '*container ls*' -and MODE -eq 'preview'){$out=('a'*64)+'|fucheng-check-v120|fucheng-check-v120|unrelated|/preview/compose.yml'}
 elseif(($Arguments -join ' ') -like '*network ls*' -and MODE -eq 'foreign_network'){$out=('b'*64)+'|fucheng_default|fucheng|foreign'}
 elseif(($Arguments -join ' ') -like '*container ls*' -and MODE -eq 'wrong_compose'){$out=('a'*64)+'|fucheng-cloudflared|fucheng|tunnel-only-v1|/other/compose.yml'}
 elseif(($Arguments -join ' ') -like '*container ls*' -and MODE -eq 'foreign'){$out=('a'*64)+'|fucheng-cloudflared|fucheng|foreign|/unknown/compose.yml'}
 elseif(($Arguments -join ' ') -like '*volume ls*' -and MODE -eq 'volume'){$out='fucheng_data|fucheng'}
 return @{exit_code=$code;timed_out=$false;stdout=$out;stderr='RAW_ERROR_SECRET'}
}
'''.replace('TOKEN', quote(token)).replace('MODE', quote(mode))
    source = source.replace("$stage='preflight'", overrides + "\n$stage='preflight'", 1)
    result = ps(tmp_path, source + '\n[IO.File]::WriteAllText(' + quote(calls) + ',(@{calls=$script:calls.ToArray();reads=$script:reads}|ConvertTo-Json -Depth 8))', timeout=20, env=env)
    return result, json.loads(calls.read_text()), tmp_path/'local data 繁中'/'Fucheng'


def test_clean_setup_creates_only_secret_file_connector_and_owned_network(tmp_path):
    result, seen, root = invoke(tmp_path)
    assert result.returncode == 0 and not result.stderr, result.stdout + result.stderr
    assert 'QUIC_REGISTERED_OBSERVED' in result.stdout
    compose = (root/'compose.yml').read_text()
    assert '--token-file' in compose and 'protocol, quic' in compose
    assert 'ports:' not in compose and 'volumes:' not in compose
    assert 'read_only: true' in compose and 'cap_drop: [ALL]' in compose
    assert 'unless-stopped' in compose and 'io.fucheng.vpc.managed' in compose
    assert (root/'tunnel.token').read_text() == TOKEN and seen['reads'] == 1
    assert len([a for a in seen['calls'] if 'up' in a]) == 1
    assert not any(word in result.stdout + result.stderr + json.dumps(seen) for word in (TOKEN, 'SECRET_SENTINEL', 'SECRET_RAW_LOG', 'RAW_ERROR_SECRET'))
    assert not any(a[0] in ('run', 'restart', 'stop', 'rm', 'exec') for a in seen['calls'])
    assert not any('fucheng-check-v120' in part for a in seen['calls'] for part in a)
    assert not any(a[:2] == ['compose', 'config'] for a in seen['calls'])


@pytest.mark.parametrize('mode', ['foreign', 'volume'])
def test_unknown_fucheng_resources_stop_before_prompt_or_write(tmp_path, mode):
    result, seen, root = invoke(tmp_path, mode=mode)
    assert result.returncode == 0 and '停止' in result.stdout
    assert 'code=UNKNOWN_FUCHENG_RESOURCE' in result.stdout
    assert seen['reads'] == 0 and not (root/'tunnel.token').exists()
    assert not any('up' in a or a[0] == 'pull' for a in seen['calls'])


@pytest.mark.parametrize('token,expected', [('not-a-token','INVALID_TOKEN_INPUT'), (base64.b64encode(json.dumps({'t':'wrong'}).encode()).decode(),'INVALID_TOKEN')])
def test_invalid_or_other_tunnel_token_is_not_saved_or_echoed(tmp_path, token, expected):
    result, seen, root = invoke(tmp_path, token=token)
    assert result.returncode == 0 and '停止' in result.stdout
    assert f'code={expected};' in result.stdout
    assert not (root/'tunnel.token').exists() and not any('up' in a for a in seen['calls'])
    assert token not in result.stdout + result.stderr


def test_rerun_preserves_existing_token_and_rejects_changed_compose(tmp_path):
    invoke(tmp_path)
    result, seen, root = invoke(tmp_path, token='must-not-be-read')
    assert result.returncode == 0 and seen['reads'] == 0 and (root/'tunnel.token').read_text() == TOKEN
    (root/'compose.yml').write_text('unmanaged change')
    result, seen, root = invoke(tmp_path)
    assert '停止' in result.stdout and not any('up' in a for a in seen['calls'])
    assert (root/'compose.yml').read_text() == 'unmanaged change'


def test_missing_image_pulls_only_pinned_digest(tmp_path):
    result, seen, root = invoke(tmp_path, mode='missing_image')
    pulls = [a for a in seen['calls'] if a[0] == 'pull']
    assert len(pulls) == 1 and '@sha256:' in pulls[0][-1] and pulls[0][-1].startswith('cloudflare/cloudflared@')
    assert not any('up' in a for a in seen['calls']), 'mock keeps image unavailable after pull; must stop'


@pytest.mark.parametrize('mode', ['foreign', 'foreign_network', 'wrong_compose'])
def test_managed_rerun_rejects_foreign_resource_labels_or_source(tmp_path, mode):
    invoke(tmp_path)
    result, seen, root = invoke(tmp_path, mode=mode)
    assert '停止' in result.stdout and seen['reads'] == 0
    assert not any('up' in a for a in seen['calls'])
    assert (root/'tunnel.token').read_text() == TOKEN


def test_existing_preview_names_are_outside_the_new_project(tmp_path):
    result, seen, root = invoke(tmp_path, mode='preview')
    assert 'QUIC_REGISTERED_OBSERVED' in result.stdout
    assert not any('fucheng-check-v120' in part for a in seen['calls'] for part in a)


def test_unknown_local_directory_is_preserved(tmp_path):
    root=tmp_path/'local data 繁中'/'Fucheng'
    root.mkdir(parents=True)
    (root/'user-file.txt').write_text('preserve me')
    result, seen, _ = invoke(tmp_path)
    assert '停止' in result.stdout and not seen['calls'] and seen['reads'] == 0
    assert list(root.iterdir()) == [root/'user-file.txt']


def test_linked_directory_is_rejected_without_touching_target(tmp_path):
    local=tmp_path/'local data 繁中';local.mkdir()
    target=tmp_path/'untouched';target.mkdir();(target/'keep.txt').write_text('keep')
    (local/'Fucheng').symlink_to(target, target_is_directory=True)
    result, seen, _ = invoke(tmp_path)
    assert '停止' in result.stdout and not seen['calls']
    assert list(target.iterdir()) == [target/'keep.txt']


def test_docker_host_override_stops_before_touching_new_project(tmp_path):
    result, seen, root = invoke(tmp_path, env={'DOCKER_HOST':'tcp://unapproved:2375'})
    assert '停止' in result.stdout and seen['reads'] == 0
    assert not any('up' in a for a in seen['calls']) and not root.exists()


def test_remote_named_pipe_context_is_not_treated_as_local(tmp_path):
    result, seen, root = invoke(tmp_path, mode='remote_pipe')
    assert '停止' in result.stdout and seen['reads'] == 0 and not root.exists()
    assert not any('up' in a for a in seen['calls'])


def test_cloudflare_copied_docker_command_extracts_only_token(tmp_path):
    command = 'docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token ' + TOKEN
    result, seen, root = invoke(tmp_path, token=command)
    assert 'QUIC_REGISTERED_OBSERVED' in result.stdout
    assert (root/'tunnel.token').read_text() == TOKEN
    assert command not in result.stdout + result.stderr + json.dumps(seen)
    assert not any(a[0] == 'run' for a in seen['calls'])


@pytest.mark.parametrize('suffix', ['; Set-Content COMMAND_SENTINEL bad', ' --token DUPLICATE', ' $(Set-Content COMMAND_SENTINEL bad)'])
def test_copied_command_never_executes_and_rejects_extra_input(tmp_path, suffix):
    command = 'docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token ' + TOKEN + suffix
    result, seen, root = invoke(tmp_path, token=command)
    assert '停止' in result.stdout and not (root/'tunnel.token').exists()
    assert not any('up' in a or a[0] == 'run' for a in seen['calls'])
    assert 'COMMAND_SENTINEL' not in result.stdout + result.stderr + json.dumps(seen)
    assert not (ROOT/'COMMAND_SENTINEL').exists() and not (tmp_path/'COMMAND_SENTINEL').exists()
