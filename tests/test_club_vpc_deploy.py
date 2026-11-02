"""Offline PowerShell deployment safety and read-only preservation contracts."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from test_club_host_one_shot import ROOT,PWSH,ps,quote

SCRIPT=ROOT/'deploy/docker/club-vpc-deploy.ps1'
pytestmark=pytest.mark.skipif(not PWSH,reason='PowerShell runtime unavailable')


def functions():
    return """$ErrorActionPreference='Stop';$t=$null;$e=$null
$a=[Management.Automation.Language.Parser]::ParseFile(SCRIPT,[ref]$t,[ref]$e)
if($e.Count){throw 'parse'}
foreach($f in $a.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$true)){. ([scriptblock]::Create($f.Extent.Text))}
""".replace('SCRIPT',quote(SCRIPT))


def data_pair(tmp_path):
    paths=[tmp_path/'source',tmp_path/'target']
    for directory in paths:
        directory.mkdir();(directory/'active.json').write_text(json.dumps({'database':'db.db'}))
        (directory/'announcement-media').mkdir();(directory/'announcement-media'/'fixture.png').write_bytes(b'fixture-image')
        with sqlite3.connect(directory/'db.db') as db:
            db.executescript("CREATE TABLE alembic_version(version_num);INSERT INTO alembic_version VALUES('0015_deployment_diagnostics');CREATE TABLE admins(id,password_hash,is_active,version);INSERT INTO admins VALUES(1,'HASH_MUST_NOT_PRINT',1,7);CREATE TABLE members(id,name);INSERT INTO members VALUES(1,'PRIVATE_NAME_MUST_NOT_PRINT');CREATE TABLE login_sessions(id);")
    (paths[0]/'local-http-synthetic.json').write_text('{}')
    with sqlite3.connect(paths[0]/'db.db') as db:db.execute('INSERT INTO login_sessions VALUES(1)')
    return paths


@pytest.mark.parametrize('damage', [None,'admin','member','media','session'])
def test_verifier_detects_business_admin_media_and_session_drift_read_only(tmp_path,damage):
    result=ps(tmp_path,functions()+"[IO.File]::WriteAllText("+quote(tmp_path/'verify.py')+",(Get-DeployVerifierSource))")
    assert result.returncode==0,result.stdout+result.stderr
    source,target=data_pair(tmp_path)
    if damage in ('admin','member','session'):
        with sqlite3.connect(target/'db.db') as db:
            db.execute({'admin':'UPDATE admins SET version=8','member':"UPDATE members SET name='changed'",'session':'INSERT INTO login_sessions VALUES(99)'}[damage])
    if damage=='media':(target/'announcement-media'/'fixture.png').write_bytes(b'wrong')
    before={p:p.read_bytes() for d in (source,target) for p in d.rglob('*') if p.is_file()}
    run=subprocess.run([sys.executable,str(tmp_path/'verify.py'),str(source),str(target)],capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    v=json.loads(run.stdout)
    assert v['ok']==(damage is None)
    assert v['source_admin_count']==v['target_admin_count']==1
    assert not any(x in run.stdout+run.stderr for x in ('HASH_MUST_NOT_PRINT','PRIVATE_NAME_MUST_NOT_PRINT'))
    assert all(p.read_bytes()==content for p,content in before.items())


def test_production_compose_has_private_origin_file_only_secrets_and_no_host_ports(tmp_path):
    run=ps(tmp_path,functions()+"$appImage='PINNED_APP';$tunnelImage='PINNED_TUNNEL';$origin='https://fucheng.momonong.workers.dev';Write-Output (Get-DeployCompose ('a'*32) $false)")
    assert run.returncode==0,run.stdout+run.stderr
    text=run.stdout
    assert 'ports:' not in text and '--protocol, quic' in text
    assert 'internal: true' in text and '172.30.98.3' in text and 'app:8000' not in text
    assert 'FUCHENG_TURNSTILE_SECRET_FILE: /run/secrets/turnstile_secret' in text
    assert 'FUCHENG_TURNSTILE_SECRET:' not in text and 'network_mode: none' in text
    assert 'backup-loop' in text and 'FUCHENG_BACKUP_KEEP: "8"' in text
    assert 'FUCHENG_TURNSTILE_HOSTNAME: fucheng.momonong.workers.dev' in text
    assert 'unless-stopped' in text and 'serve' in text


@pytest.mark.parametrize('left,right,overlap',[('172.30.98.0/24','172.30.0.0/16',True),('172.30.98.0/24','192.168.0.0/24',False),('172.30.98.0/24','172.30.98.2/32',True)])
def test_subnet_overlap_is_checked_without_route_changes(tmp_path,left,right,overlap):
    run=ps(tmp_path,functions()+"Write-Output (Test-DeployOverlap "+quote(left)+' '+quote(right)+')')
    assert run.returncode==0,run.stdout+run.stderr
    assert run.stdout.strip()==str(overlap)


TOKEN='eyJhIjoiZml4dHVyZSIsInQiOiJmYTQ1OGNkYi0wYmY0LTQzYTItODllZi1lOWQxNWIzNDhkMTQiLCJzIjoiTkVWRVJfUFJJTlRfVE9LRU4ifQ=='
KEY='0x4AAAAA_NEVER_PRINT_SITEKEY_12345'
SECRET='0x4AAAAA_NEVER_PRINT_SECRET_12345'


def full_run(tmp_path,mode='ok'):
    source=SCRIPT.read_text(encoding='utf-8-sig')
    overrides=r'''
function Assert-VpcWindows {}
function Assert-VpcOwner {}
function Set-VpcPrivatePath {}
function Get-Command {return [pscustomobject]@{Source='fixture-docker.exe'}}
function Get-NetRoute {return [pscustomobject]@{DestinationPrefix='192.168.1.0/24'}}
function Start-Sleep {}
function Test-DeployPublic {return (MODE -notin @('public_fail','stop_timeout','stop_running'))}
$script:stopped=@{}
$script:reads=0;$script:calls=New-Object 'System.Collections.Generic.List[object]';$script:sourceRunning=$true;$script:stack=$false;$script:connector=$false;$script:volume=$false;$script:jobs=@()
function Read-Host {param($Prompt,[switch]$AsSecureString)
 $script:reads++;if(MODE -eq 'cancel_input' -and $script:reads -eq 3){throw 'SYNTHETIC_CANCEL'}
 $value=if($Prompt -like '*Tunnel token*'){TOKEN}elseif($Prompt -like '*sitekey*'){KEY}elseif(MODE -eq 'invalid_secret'){'bad'}else{SECRET}
 if(MODE -eq 'concurrent' -and $Prompt -like '*Turnstile secret*'){[IO.File]::WriteAllText((Join-Path $root 'deploy-journal.json'),'OTHER_OWNER_RECEIPT')}
 return (ConvertTo-SecureString $value -AsPlainText -Force)
}
function Invoke-ProbeDocker([string[]]$Arguments,[int]$Limit=10){
 $script:calls.Add(@($Arguments));$out='';$code=0;$timeout=$false;$joined=$Arguments -join ' '
 if($Arguments[0] -eq 'context'){$out='npipe:////./pipe/dockerDesktopLinuxEngine'}
 elseif($Arguments[0] -eq 'info'){$out='linux|x86_64'}
 elseif($Arguments[0] -eq 'image'){$out='sha256:'+('1'*64)+'|linux|amd64';if($Arguments[-1] -like 'cloudflare/*'){$out='sha256:'+('2'*64)+'|linux|amd64'}}
 elseif($joined -like '*container ls*' -and $Arguments -contains '--quiet') {if($script:sourceRunning){$out='a'*64};if(MODE -eq 'writer'){$out='e'*64}}
 elseif($joined -like '*container ls*') {
  $lines=@();if(MODE -eq 'old' -and !$script:connector){$lines+=(('f'*64)+'|fucheng-cloudflared|fucheng|tunnel-only-v1||'+$composePath+'|cloudflared')};foreach($job in $script:jobs){$lines+=($job.id+'|'+$job.name+'|fucheng|full-v1|'+$journal.id+'||')}
  if($script:stack){$lines+=(('b'*64)+'|fucheng-app|fucheng|full-v1|'+$journal.id+'|'+$composePath+'|app');$lines+=(('c'*64)+'|fucheng-backup|fucheng|full-v1|'+$journal.id+'|'+$composePath+'|backup')}
  if($script:connector){$lines+=(('d'*64)+'|fucheng-cloudflared|fucheng|full-v1|'+$journal.id+'|'+$composePath+'|cloudflared')}
  if(MODE -eq 'foreign_volume'){$script:volume=$true};$out=$lines -join "`n"
 }
 elseif($joined -like '*network ls*' -and $Arguments -contains '--format' -and MODE -eq 'old'){$out=('8'*64)+'|fucheng_default|fucheng|tunnel-only-v1|'}
 elseif($Arguments[0] -eq 'network' -and $Arguments[1] -eq 'inspect'){$out='{}'}
 elseif($joined -like '*volume ls*') {if($script:volume){$owner=if($journal){$journal.id}else{'foreign'};$out='fucheng_data|fucheng_data|fucheng|full-v1|'+$owner}}
 elseif($Arguments[0] -eq 'volume' -and $Arguments[1] -eq 'create'){$script:volume=$true;$out='fucheng_data'}
 elseif($Arguments[0] -eq 'volume' -and $Arguments[1] -eq 'inspect'){$out=@{'com.docker.compose.project'='fucheng';'io.fucheng.vpc.managed'='full-v1';'io.fucheng.vpc.deployment'=$journal.id}|ConvertTo-Json -Compress}
 elseif($Arguments[0] -eq 'inspect'){
  $format=$Arguments[$Arguments.IndexOf('--format')+1];$target=$Arguments[-1]
  if($target -eq 'fucheng-check-v120'){
   $id=if(MODE -eq 'wrong_source'){'9'*64}else{'a'*64}
   $out=@{id=$id;image=('sha256:'+('1'*64));state=$(if($script:sourceRunning){'running'}else{'exited'});command=@('serve');env=@('FUCHENG_LOCAL_HTTP_PREVIEW=true','FUCHENG_PUBLIC_ORIGIN=http://localhost:8052','FUCHENG_COOKIE_SECURE=false','FUCHENG_PROXY_KIND=local','FUCHENG_BASE_PATH=','FUCHENG_TRUSTED_PROXY=');mounts=@(@{Type='volume';Name='fucheng-check-v120_data';Destination='/data';RW=$true});ports=@{'8000/tcp'=@(@{HostIp='127.0.0.1';HostPort='8052'})}}|ConvertTo-Json -Depth 7 -Compress
  }elseif($target -eq ('e'*64) -or $format -like '*"mounts"*'){$out=@{id=$target;mounts=@(@{Type='volume';Name='fucheng-check-v120_data';Destination='/data';RW=$true})}|ConvertTo-Json -Depth 6 -Compress}
  elseif($format -eq '{{.Image}}'){$out='sha256:'+$(if($target -eq ('d'*64)){'2'*64}else{'1'*64})}
  elseif($format -eq '{{.State.Status}}'){$out=if($script:stopped.ContainsKey($target)){'exited'}else{'running'}}
  elseif($format -like '*Health*'){$out='running|healthy'}
  else{$out='exited|0'}
 }
 elseif($Arguments[0] -eq 'stop'){
  if($Arguments[-1] -eq ('a'*64)){$script:sourceRunning=$false}
  elseif($Arguments[-1] -eq ('b'*64) -and MODE -eq 'stop_timeout'){$code=$null;$timeout=$true}
  elseif(!($Arguments[-1] -eq ('b'*64) -and MODE -eq 'stop_running')){$script:stopped[$Arguments[-1]]=$true}
 }
 elseif($Arguments[0] -eq 'start'){if($Arguments[-1] -eq ('a'*64)){$script:sourceRunning=$true}}
 elseif($Arguments[0] -eq 'run'){
  $name=$Arguments[$Arguments.IndexOf('--name')+1];$id=('{0:x64}' -f (100+$script:jobs.Count));$script:jobs+=,[pscustomobject]@{name=$name;id=$id}
  $out=$id
  if($name.EndsWith('-backup')){
   $filename='manual-20261101T010000000000Z-12345678.db';$db=Join-Path $checkpointDir $filename;$media=Join-Path $checkpointDir ($filename -replace '\.db$','.media.tar');[IO.File]::WriteAllText($db,'synthetic db');[IO.File]::WriteAllText($media,'synthetic media')
   $metadata=@{file=$filename;media_file=[IO.Path]::GetFileName($media);sha256=(Get-FileHash $db).Hash.ToLowerInvariant();media_sha256=(Get-FileHash $media).Hash.ToLowerInvariant();revision='0015_deployment_diagnostics';restore_config=@{image_ref=$appImage}}
   [IO.File]::WriteAllText(($db -replace '\.db$','.json'),($metadata|ConvertTo-Json -Depth 4))
  }
  if(MODE -eq 'import_unknown' -and $name.EndsWith('-import')){$code=$null;$timeout=$true}
 }
 elseif($Arguments[0] -eq 'logs'){$out=@{ok=$true;schema_match=$true;integrity_ok=$true;fk_ok=$true;revision_match=$true;business_match=$true;admin_match=$true;target_sessions_zero=$true;media_match=$true;source_preview_marked=$true;target_preview_unmarked=$true;source_admin_count=1;target_admin_count=1}|ConvertTo-Json -Compress}
 elseif($Arguments[0] -eq 'compose' -and $Arguments -contains 'up'){if($Arguments[-1] -eq 'cloudflared'){$script:connector=$true}else{$script:stack=$true}}
 return @{exit_code=$code;timed_out=$timeout;stdout=$out;stderr='NEVER_PRINT_RAW_DOCKER_ERROR'}
}
'''.replace('MODE',quote(mode)).replace('TOKEN',quote(TOKEN)).replace('KEY',quote(KEY)).replace('SECRET',quote(SECRET))
    # Insert only at main entry; production functions and state machine remain intact.
    source=source.replace('$docker=$null;$lock=$null;$journal=$null;',overrides+'\n$docker=$null;$lock=$null;$journal=$null;',1)
    calls=tmp_path/'full-calls.json'
    result=ps(tmp_path,source+'\n[IO.File]::WriteAllText('+quote(calls)+',(@{calls=$script:calls.ToArray();reads=$script:reads;source_running=$script:sourceRunning}|ConvertTo-Json -Depth 8))',timeout=25)
    assert calls.exists(),result.stdout+result.stderr
    return result,json.loads(calls.read_text()),tmp_path/'local data 繁中'/'Fucheng'


def test_full_deployment_orders_preservation_before_public_connector(tmp_path):
    result,seen,root=full_run(tmp_path)
    assert result.returncode==0 and not result.stderr,result.stdout+result.stderr
    assert '階段：COMPLETE' in result.stdout,result.stdout
    journal=json.loads((root/'deploy-journal.json').read_text())
    assert journal['phase']=='COMPLETE' and [o['name'] for o in journal['operations']]==['backup','import','restore','verify']
    calls=seen['calls'];jobs=[a for a in calls if a[0]=='run']
    assert len(jobs)==4 and all('--rm' not in a for a in jobs)
    assert all(a[a.index('--network')+1]=='none' for a in jobs)
    ups=[a for a in calls if a[0]=='compose' and 'up' in a]
    assert ups[0][-2:]==['app','backup'] and ups[1][-1]=='cloudflared'
    assert not seen['source_running'] and (root/'tunnel.token').read_text()==TOKEN
    assert not any(s in result.stdout+result.stderr+json.dumps(seen) for s in (TOKEN,KEY,SECRET,'NEVER_PRINT_RAW_DOCKER_ERROR'))
    assert not any(a[0] in ('rm','prune') or 'init' in a or 'migrate' in a for a in calls)


@pytest.mark.parametrize('mode',['invalid_secret','cancel_input'])
def test_input_failure_leaves_no_new_root_and_can_be_reentered(tmp_path,mode):
    result,seen,root=full_run(tmp_path,mode)
    assert '停止' in result.stdout and not root.exists()
    assert not any(a[0] in ('stop','run','start') for a in seen['calls'])
    good,_,_=full_run(tmp_path)
    assert '階段：COMPLETE' in good.stdout,good.stdout


@pytest.mark.parametrize('mode',['foreign_volume','writer'])
def test_unknown_volume_or_other_source_writer_stops_without_inputs_or_mutation(tmp_path,mode):
    result,seen,root=full_run(tmp_path,mode)
    assert '停止' in result.stdout and seen['reads']==0 and not root.exists()
    assert not any(a[0] in ('stop','run','volume') and (a[0]!='volume' or a[1]=='create') for a in seen['calls'])


@pytest.mark.parametrize('mode',['public_fail','import_unknown'])
def test_failure_preserves_journal_restores_preview_and_never_blindly_restores(tmp_path,mode):
    result,seen,root=full_run(tmp_path,mode)
    assert '停止' in result.stdout and seen['source_running'],result.stdout
    journal=json.loads((root/'deploy-journal.json').read_text())
    assert journal['phase']=='FAILED' and journal['preview_recovered']
    rerun,again,_=full_run(tmp_path)
    assert 'PARTIAL_DEPLOYMENT_REVIEW_REQUIRED' in rerun.stdout,rerun.stdout
    assert not any(a[0] in ('run','start','stop') or 'up' in a for a in again['calls'])


@pytest.mark.parametrize('mode', ['stop_timeout', 'stop_running'])
def test_unconfirmed_new_stack_stop_never_restarts_preview(tmp_path, mode):
    result, seen, root = full_run(tmp_path, mode)
    assert '停止' in result.stdout, result.stdout
    assert not seen['source_running'], result.stdout
    assert not any(a[0] == 'start' and a[-1] == 'a' * 64 for a in seen['calls'])
    journal = json.loads((root / 'deploy-journal.json').read_text())
    assert journal['phase'] == 'FAILED' and not journal['preview_recovered']
    assert '新 stack 停止未確認' in result.stdout


def prepare_old(tmp_path):
    root=tmp_path/'local data 繁中'/'Fucheng';root.mkdir(parents=True)
    code=functions()+"$utf8=New-Object Text.UTF8Encoding($false);$text=Get-DeployOldCompose;[IO.File]::WriteAllText("+quote(root/'compose.yml')+",$text,$utf8);[IO.File]::WriteAllText("+quote(root/'owner.txt')+",('fucheng-vpc-tunnel-only-v1|'+(Get-VpcHash $text)),$utf8)"
    result=ps(tmp_path,code)
    assert result.returncode==0,result.stdout+result.stderr
    (root/'tunnel.token').write_text(TOKEN)
    return root


def test_owned_connector_upgrades_and_preserves_original_files_token(tmp_path):
    root=prepare_old(tmp_path);before=(root/'compose.yml').read_bytes()
    result,seen,_=full_run(tmp_path,'old')
    assert '階段：COMPLETE' in result.stdout,result.stdout
    assert seen['reads']==2 and (root/'tunnel.token').read_text()==TOKEN
    assert (root/'connector-compose.before.yml').read_bytes()==before
    journal=json.loads((root/'deploy-journal.json').read_text())
    assert journal['old_default'] is True
    assert 'external: true' in (root/'compose.yml').read_text()
    assert any(a[0]=='stop' and a[-1]=='f'*64 for a in seen['calls'])


def test_invalid_secret_with_old_connector_does_not_write_keys_or_stop_it(tmp_path):
    root=prepare_old(tmp_path);before={p.name:p.read_bytes() for p in root.iterdir()}
    result,seen,_=full_run(tmp_path,'invalid_secret')
    assert 'INVALID_TURNSTILE_SECRET' in result.stdout
    assert not any(a[0] in ('stop','run','start') for a in seen['calls'])
    assert {p.name:p.read_bytes() for p in root.iterdir()}==before


def test_complete_rerun_does_not_restore_or_restart_source(tmp_path):
    first,_,root=full_run(tmp_path)
    assert '階段：COMPLETE' in first.stdout
    result,seen,_=full_run(tmp_path)
    assert '既有正式部署健康核對通過' in result.stdout,result.stdout
    assert not any(a[0] in ('run','start','stop') or 'up' in a for a in seen['calls'])


@pytest.mark.parametrize('damage,expected',[('image','SOURCE_IDENTITY_MISMATCH'),('mount','SOURCE_VOLUME_MISMATCH'),('preview','SOURCE_PREVIEW_MISMATCH'),('port','SOURCE_PORT_MISMATCH')])
def test_source_identity_volume_preview_and_loopback_are_required(tmp_path,damage,expected):
    value={'id':'a'*64,'image':'sha256:'+'1'*64,'state':'running','command':['serve'],'env':['FUCHENG_LOCAL_HTTP_PREVIEW=true','FUCHENG_PUBLIC_ORIGIN=http://localhost:8052','FUCHENG_COOKIE_SECURE=false','FUCHENG_PROXY_KIND=local'],'mounts':[{'Type':'volume','Name':'fucheng-check-v120_data','Destination':'/data','RW':True}],'ports':{'8000/tcp':[{'HostIp':'127.0.0.1','HostPort':'8052'}]}}
    if damage=='image':value['image']='sha256:'+'9'*64
    if damage=='mount':value['mounts'][0]['Name']='other_private_data'
    if damage=='preview':value['env'][0]='FUCHENG_LOCAL_HTTP_PREVIEW=false'
    if damage=='port':value['ports']['8000/tcp'][0]['HostIp']='0.0.0.0'
    result=ps(tmp_path,functions()+"$appImageId='sha256:"+'1'*64+"';function Invoke-VpcChecked {return "+quote(json.dumps(value))+"};try{$null=Get-DeploySource;throw 'accepted'}catch{Write-Output $_.Exception.Message}")
    assert result.returncode==0 and result.stdout.strip()==expected,result.stdout+result.stderr


def test_concurrent_journal_appearing_during_input_is_never_overwritten(tmp_path):
    root=prepare_old(tmp_path)
    result,seen,_=full_run(tmp_path,'concurrent')
    assert 'CONCURRENT_SETUP_DETECTED' in result.stdout,result.stdout
    assert (root/'deploy-journal.json').read_text()=='OTHER_OWNER_RECEIPT'
    assert not any(a[0] in ('stop','run','start') for a in seen['calls'])
    assert not (root/'turnstile.secret').exists() and not (root/'protected.env').exists()
