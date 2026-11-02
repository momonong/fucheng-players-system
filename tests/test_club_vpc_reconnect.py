"""Recovery must recompare stopped data and only restart existing owned containers."""
import json
import pytest
from test_club_host_one_shot import ROOT,PWSH,ps,quote

SCRIPT=ROOT/'deploy/docker/club-vpc-reconnect.ps1'
pytestmark=pytest.mark.skipif(not PWSH,reason='PowerShell runtime unavailable')

def invoke(tmp_path,mode='ok'):
 source=SCRIPT.read_text(encoding='utf-8-sig')
 calls=tmp_path/'calls.json'
 override=r'''
function Assert-VpcWindows {}
function Get-VpcCallerSid {return 'S-1-5-21-111-222-333-1001'}
function Get-VpcAclSnapshot([string]$Path) {
 $owner=if($script:mode -eq 'admin_owner'){'S-1-5-32-544'}elseif($script:mode -eq 'system_owner'){'S-1-5-18'}else{'S-1-5-21-111-222-333-1001'}
 $rules=@('S-1-5-21-111-222-333-1001','S-1-5-18','S-1-5-32-544')
 if($script:mode -eq 'broad_acl' -and [IO.Path]::GetFileName($Path) -eq 'compose.yml'){$rules+=,'S-1-1-0'}
 return [pscustomobject]@{owner=$owner;protected=$true;rules=@($rules|ForEach-Object {[pscustomobject]@{sid=$_;allow=$true}})}
}
function Get-Command {return [pscustomobject]@{Source='fixture-docker.exe'}}
function Start-Sleep {}
$script:calls=[Collections.Generic.List[object]]::new()
$script:preview=$true;$script:mode=MODE;if($script:mode -eq 'off_fail'){$script:preview=$false}
$script:ids=@{'fucheng-app'=('b'*64);'fucheng-backup'=('c'*64);'fucheng-cloudflared'=('d'*64)}
$script:states=@{('b'*64)='exited';('c'*64)='exited';('d'*64)='exited'}
$r=Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)) 'Fucheng'
$null=New-Item -ItemType Directory $r
$jid='e'*32
$fixture=[pscustomobject]@{version=1;id=$jid;source_id=('a'*64);source_was_running=$true;image_id=('sha256:'+('1'*64));target_volume='fucheng_data';old_default=$false;phase='FAILED';failure_code='PUBLIC_HEALTH_UNCONFIRMED';verification=@{business_match=$true;admin_match=$true;media_match=$true};operations=@([pscustomobject]@{name='verify';id=('f'*64);container=('fucheng-op-'+$jid.Substring(0,12)+'-verify');status='complete';exit_code=0})}
if($script:mode -eq 'bad_receipt'){$fixture.operations[0].exit_code=1}
if($script:mode -eq 'complete'){$fixture.phase='COMPLETE';$fixture.failure_code=$null;$script:preview=$false;foreach($k in @($script:states.Keys)){$script:states[$k]='running'}}
$text=Get-DeployCompose $jid $false
[IO.File]::WriteAllText((Join-Path $r 'compose.yml'),$text)
[IO.File]::WriteAllText((Join-Path $r 'owner.txt'),('fucheng-vpc-full-v1|'+(Get-VpcHash $text)))
[IO.File]::WriteAllText((Join-Path $r 'deploy-journal.json'),($fixture|ConvertTo-Json -Depth 9))
[IO.File]::WriteAllText((Join-Path $r 'setup.lock'),'')
if($script:mode -eq 'bad_compose'){[IO.File]::WriteAllText((Join-Path $r 'compose.yml'),'preserve-user-file')}
function Get-DeployResources {
 $items=@();foreach($n in $script:ids.Keys){$items+=,[pscustomobject]@{name=$n;id=$script:ids[$n];old=$false}}
 return @{containers=$items;networks=@();volumes=@('fucheng_data')}
}
function Get-DeploySource {
 return [pscustomobject]@{id=('a'*64);image=('sha256:'+('1'*64));state=$(if($script:preview){'running'}else{'exited'})}
}
function Assert-DeployNoWriter {}
function Test-DeployPublic {return $script:mode -cnotin @('public_fail','stop_unknown','off_fail')}
function Invoke-VpcChecked([string[]]$Arguments,[int]$Limit=15){
 $script:calls.Add(@($Arguments));$joined=$Arguments -join ' '
 if($Arguments[0] -eq 'context'){return 'npipe:////./pipe/dockerDesktopLinuxEngine'}
 if($Arguments[0] -eq 'image'){if($Arguments[-1] -ceq $appImage){return 'sha256:'+('1'*64)};return 'sha256:'+('2'*64)}
 if($Arguments[0] -eq 'container'){if($script:mode -eq 'writer'){return ('9'*64)};return ''}
 if($Arguments[0] -eq 'inspect'){
  if($joined -like '*"readonly"*'){
   $mounts=@(@{Type='volume';Name='fucheng-check-v120_data';Destination='/source';RW=$false},@{Type='volume';Name='fucheng_data';Destination='/target';RW=$false})
   if($script:mode -eq 'writable_verifier'){$mounts[0].RW=$true}
   return (@{image=('sha256:'+('1'*64));entry=@('python');cmd=@('-c',(Get-DeployVerifierSource));network='none';readonly=$true;mounts=$mounts}|ConvertTo-Json -Depth 8 -Compress)
  }
  $id=$Arguments[-1];if($script:ids.ContainsKey($id)){$id=$script:ids[$id]}
  if($joined -like '*Health*'){return $script:states[$id]+'|healthy'}
  return $script:states[$id]
 }
 if($Arguments[0] -eq 'start'){
  $id=$Arguments[-1]
  if($Arguments -contains '--attach'){
   $valid=($script:mode -ne 'drift')
   return (@{ok=$valid;schema_match=$true;integrity_ok=$true;fk_ok=$true;revision_match=$true;business_match=$valid;admin_match=$true;target_sessions_zero=$true;media_match=$true;source_preview_marked=$true;target_preview_unmarked=$true;source_admin_count=1;target_admin_count=1}|ConvertTo-Json -Compress)
  }
  if($id -ceq ('a'*64)){$script:preview=$true}else{$script:states[$id]='running'};return ''
 }
 if($Arguments[0] -eq 'stop'){
  $id=$Arguments[-1]
  if($id -ceq ('a'*64)){$script:preview=$false}else{if($script:mode -eq 'stop_unknown' -and $id -ceq ('d'*64)){throw 'DOCKER_COMMAND_UNCONFIRMED'};$script:states[$id]='exited'};return ''
 }
 throw 'UNEXPECTED_DOCKER_ACTION'
}
'''.replace('MODE',quote(mode))
 source=source.replace('$docker=$null;$lock=$null;$journal=$null;',override+'\n$docker=$null;$lock=$null;$journal=$null;',1)
 result=ps(tmp_path,source+'\n[IO.File]::WriteAllText('+quote(calls)+',(@{calls=$script:calls.ToArray();preview=$script:preview;states=$script:states}|ConvertTo-Json -Depth 9))',timeout=25)
 assert calls.exists(),result.stdout+result.stderr
 return result,json.loads(calls.read_text()),tmp_path/'local data 繁中'/'Fucheng'

def test_stopped_data_is_verified_before_only_existing_stack_is_started(tmp_path):
 result,seen,root=invoke(tmp_path)
 assert result.returncode==0 and not result.stderr,result.stdout+result.stderr
 assert 'COMPLETE：' in result.stdout,result.stdout
 assert not seen['preview'] and set(seen['states'].values())=={'running'}
 journal=json.loads((root/'deploy-journal.json').read_text())
 assert journal['phase']=='COMPLETE' and journal['failure_code'] is None
 commands=seen['calls'];starts=[a for a in commands if a[0]=='start']
 assert starts[0]==['start','--attach','f'*64]
 assert [a[-1] for a in starts[1:]]==['b'*64,'c'*64,'d'*64]
 assert not any(a[0] in ('run','create','compose','rm','prune') or any(x in a for x in ('restore','import-backup','init','migrate')) for a in commands)
 assert not any(a[0] in ('logs','exec') for a in commands)

@pytest.mark.parametrize('mode,code',[('bad_receipt','VERIFY_RECEIPT_INVALID'),('bad_compose','UNKNOWN_MANAGED_FILES'),('writable_verifier','VERIFY_CONTAINER_MISMATCH'),('writer','OTHER_TARGET_WRITER')])
def test_unsafe_scope_stops_before_stopping_source(tmp_path,mode,code):
 result,seen,root=invoke(tmp_path,mode)
 assert 'code='+code in result.stdout,result.stdout+result.stderr
 assert seen['preview'] and not any(a[0] in ('start','stop') for a in seen['calls'])
 assert json.loads((root/'deploy-journal.json').read_text())['phase']=='FAILED'

@pytest.mark.parametrize('mode,code',[('drift','DATA_CHANGED_REVIEW_REQUIRED'),('public_fail','PUBLIC_HEALTH_UNCONFIRMED')])
def test_failure_never_overwrites_data_and_restarts_original_preview(tmp_path,mode,code):
 result,seen,root=invoke(tmp_path,mode)
 assert 'code='+code in result.stdout,result.stdout+result.stderr
 assert seen['preview'] and set(seen['states'].values())=={'exited'}
 assert not any(a[0] in ('run','create','compose') for a in seen['calls'])
 assert json.loads((root/'deploy-journal.json').read_text())['phase']=='FAILED'
 if mode=='drift':assert not any(a[0]=='start' and a[-1] in ('b'*64,'c'*64,'d'*64) for a in seen['calls'])

def test_complete_rerun_is_read_only(tmp_path):
 result,seen,_=invoke(tmp_path,'complete')
 assert '既有正式部署健康通過' in result.stdout,result.stdout+result.stderr
 assert not any(a[0] in ('start','stop','run','create','compose') for a in seen['calls'])


def test_uncertain_stop_never_starts_second_writer_preview(tmp_path):
 result,seen,_=invoke(tmp_path,'stop_unknown')
 assert '未啟動原 preview' in result.stdout,result.stdout+result.stderr
 assert not seen['preview']
 assert not any(a[0]=='start' and a[-1]=='a'*64 for a in seen['calls'])


def test_originally_stopped_preview_remains_stopped_after_public_failure(tmp_path):
 result,seen,_=invoke(tmp_path,'off_fail')
 assert 'PUBLIC_HEALTH_UNCONFIRMED' in result.stdout,result.stdout+result.stderr
 assert not seen['preview'] and set(seen['states'].values())=={'exited'}
 assert not any(a[0] in ('start','stop') and a[-1]=='a'*64 for a in seen['calls'])


@pytest.mark.parametrize('mode',['admin_owner','system_owner'])
def test_private_windows_group_owned_files_resume_without_permission_changes(tmp_path,mode):
 result,seen,_=invoke(tmp_path,mode)
 assert 'COMPLETE：' in result.stdout,result.stdout+result.stderr
 assert 'private_acl=True' in result.stdout
 assert set(seen['states'].values())=={'running'}
 assert not seen['preview']


def test_nonprivate_metadata_stops_before_any_container_action(tmp_path):
 result,seen,_=invoke(tmp_path,'broad_acl')
 assert 'PRIVATE_ACL_UNCONFIRMED' in result.stdout,result.stdout+result.stderr
 assert 'compose.yml' in result.stdout and 'private_acl=False' in result.stdout
 assert seen['preview'] and not any(a[0] in ('start','stop','run') for a in seen['calls'])
