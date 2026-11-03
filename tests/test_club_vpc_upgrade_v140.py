"""Focused offline regressions; no Docker daemon or Windows host is touched."""
import json, os, subprocess
from pathlib import Path
import pytest

HERE=Path(__file__).resolve().parents[1]
SCRIPT=HERE/'deploy/docker/club-vpc-upgrade-1.4.0.ps1'
PWSH=Path(os.environ.get('FUCHENG_TEST_PWSH','pwsh'))
if not __import__('shutil').which(str(PWSH)):
    pytest.skip('PowerShell runtime is not configured', allow_module_level=True)
OLD='momonong/fucheng-players-system@sha256:9b8931bd9042d932cbb0ff4f3b30fba82390d9478bac38a9444780efbe919e1e'
OLD_ID='sha256:63da2c4ddd162c56d2e68e7a7b88a02978081e857b1b850620af109c43564925'
NEW='momonong/fucheng-players-system@sha256:'+'a'*64
NEW_ID='sha256:'+'b'*64

def q(x):return "'"+str(x).replace("'","''")+"'"
def ps(tmp_path, body):
    assert SCRIPT.exists(), 'Missing guarded code-only updater'
    f=tmp_path/'run.ps1';f.write_text(". "+q(SCRIPT)+"\n"+body,encoding='utf-8-sig')
    return subprocess.run([str(PWSH),'-NoProfile','-File',str(f)],capture_output=True,text=True,timeout=30)

def invoke(tmp_path,mode='ok'):
    calls=tmp_path/'calls.json';root=tmp_path/'球館 private'
    body=r'''
$script:mode=MODE;$script:calls=[Collections.Generic.List[object]]::new();$script:r=ROOT
$null=New-Item -ItemType Directory $r
$null=New-Item -ItemType Directory (Join-Path $r 'backup')
function Get-UpgradeRoot {return $script:r}
function Assert-VpcWindows {}
function Assert-VpcNoLink([string]$Path) {}
function Assert-VpcOwner([string]$Path) {if($script:mode -eq 'acl' -and $Path.EndsWith('protected.env')){throw 'PRIVATE_ACL_UNCONFIRMED'}}
function Set-VpcPrivatePath {}
function Get-Command {return [pscustomobject]@{Source='fixture-docker.exe'}}
function Start-Sleep {}
$jid='e'*32
$old=[pscustomobject]@{version=1;phase='COMPLETE';id=$jid;source_id=('f'*64);image_id=$originalImageId;target_volume='fucheng_data';old_default=$false;verification=@{business_match=$true;admin_match=$true;media_match=$true};operations=@()}
if($mode -eq 'manifest_store'){$old.image_id=($originalImage -split '@')[1]}
$text=Get-DeployCompose $jid $false
foreach($name in @('setup.lock','protected.env','turnstile.secret','tunnel.token')){[IO.File]::WriteAllText((Join-Path $r $name),'DO_NOT_READ_SECRET')}
[IO.File]::WriteAllText((Join-Path $r 'compose.yml'),$text)
[IO.File]::WriteAllText((Join-Path $r 'owner.txt'),('fucheng-vpc-full-v1|'+(Get-VpcHash $text)))
[IO.File]::WriteAllText((Join-Path $r 'deploy-journal.json'),($old|ConvertTo-Json -Depth 8))
$script:oldJournal=[IO.File]::ReadAllText((Join-Path $r 'deploy-journal.json'))
$priorDir=Join-Path $r ('backup/upgrade-'+('c'*32));$null=New-Item -ItemType Directory $priorDir
$summary=@{ok=$true;schema='0015_deployment_diagnostics';digest=('c'*64);admin_count=1;media_digest=('e'*64);integrity_ok=$true;fk_ok=$true}
function FixtureReceipt([string]$Id,[string]$Source,[string]$SourceId,[string]$Target,[string]$TargetId,[string]$Digit) {
 $ops=@();$i=0;foreach($n in @('backup','before','after')){$i++;$ops+=@{name=$n;container=('fucheng-upgrade-'+$Id+'-'+$n);id=(([string]($Digit+$i))*32);status='complete';exit_code=0}}
 return @{version=1;id=$Id;deployment_id=$jid;old_image=$Source;old_image_id=$SourceId;target_image=$Target;target_image_id=$TargetId;phase='COMPLETE';operations=$ops;before=$summary.Clone();after=$summary.Clone();backup=@{file='manual-20261103T000000Z-12345678.db';sha256=('a'*64);media_file='manual-20261103T000000Z-12345678.media.tar';media_sha256=('b'*64);schema='0015_deployment_diagnostics';operation_id=$ops[0].id};failure_code=$null;stop_confirmed=$null}
}
$prior=FixtureReceipt ('c'*32) $originalImage $originalImageId $oldImage $oldImageId '6'
if($mode -eq 'source_drift'){$prior.target_image_id='sha256:'+('0'*64)}
if($mode -eq 'receipt_digest'){$prior.after.digest='0'*64}
if($mode -eq 'prior_partial'){$prior.phase='BACKUP_PENDING'}
if($mode -eq 'prior_operation'){$prior.operations[1].status='create_pending'}
if($mode -eq 'prior_deployment'){$prior.deployment_id='0'*32}
[IO.File]::WriteAllText((Join-Path $priorDir 'upgrade-journal.json'),($prior|ConvertTo-Json -Depth 10))
$originalText=$text.Replace($oldImage,$originalImage)
[IO.File]::WriteAllText((Join-Path $priorDir 'compose.before.yml'),$originalText)
[IO.File]::WriteAllText((Join-Path $priorDir 'owner.before.txt'),('fucheng-vpc-full-v1|'+(Get-VpcHash $originalText)))
$script:priorJournal=[IO.File]::ReadAllText((Join-Path $priorDir 'upgrade-journal.json'))
if($mode -eq 'prior_next'){[IO.File]::WriteAllText((Join-Path $priorDir 'upgrade-journal.json.next'),'unknown')}
if($mode -eq 'compose_next'){[IO.File]::WriteAllText((Join-Path $r 'compose.yml.upgrade-next'),'unknown')}
if($mode -eq 'unknown_upgrade'){$null=New-Item -ItemType Directory (Join-Path $r ('backup/upgrade-'+('d'*32)))}
if($mode -eq 'multiple_prior'){
 $d=Join-Path $r ('backup/upgrade-'+('d'*32));$null=New-Item -ItemType Directory $d
 $p=FixtureReceipt ('d'*32) $originalImage $originalImageId $oldImage $oldImageId '7'
 [IO.File]::WriteAllText((Join-Path $d 'upgrade-journal.json'),($p|ConvertTo-Json -Depth 10))
}

if($mode -eq 'recipe'){[IO.File]::AppendAllText((Join-Path $r 'compose.yml'),'DRIFT')}
$script:states=@{app='running';backup='running';cloudflared='running'}
$script:realIdentity=${function:Assert-UpgradeIdentity}
function Get-UpgradeContainer([string]$Name){
 $service=$Name.Substring(8);$id=@{app='1';backup='2';cloudflared='3'}[$service]*64
 if($script:mixed -and $service -eq 'backup' -and $mode -eq 'compose_missing_backup'){throw 'DOCKER_COMMAND_UNCONFIRMED'}
 $mounts=@();if($service -ne 'cloudflared'){$mounts+=@{Type='volume';Name='fucheng_data';Destination='/data';RW=$true}}
 $extra=if($service -eq 'app'){@('/run/secrets/turnstile_secret','turnstile.secret',$false)}elseif($service -eq 'backup'){@('/backups','backup/live',$true)}else{@('/run/secrets/tunnel_token','tunnel.token',$false)}
 $mounts+=@{Type='bind';Source=(Join-Path $root $extra[1]);Destination=$extra[0];RW=$extra[2]}
 $networks=if($service -eq 'backup'){@{none=@{}}}else{@{fucheng_origin=@{IPAddress=$(if($service -eq 'app'){'172.30.98.2'}else{'172.30.98.3'})};fucheng_default=@{}}}
 $ref=if($service -eq 'cloudflared'){$tunnelImage}elseif($script:mixed -and $service -eq 'app'){$TargetImage}else{$oldImage}
 $image=if($service -eq 'cloudflared'){$tunnelImageId}elseif($script:mixed -and $service -eq 'app'){$ExpectedImageId}else{$oldImageId}
 if($mode -eq 'manifest_store'){$image=($ref -split '@')[1]}
 if($script:mixed -and $service -eq 'backup' -and $mode -eq 'compose_foreign_backup'){$image='sha256:'+('0'*64)}
 return [pscustomobject]@{id=$id;name=('/'+$Name);image=$image;ref=$ref;state=$script:states[$service];health=$(if($service -eq 'cloudflared'){$null}else{'healthy'});readonly=$true;user='10001:10001';ports=[pscustomobject]@{};network_mode=$(if($service -eq 'backup'){'none'}else{'fucheng_default'});command=$(if($service -eq 'app'){@('serve')}elseif($service -eq 'backup'){@('backup-loop')}else{@('tunnel','--no-autoupdate','--protocol','quic','run','--token-file','/run/secrets/tunnel_token')});mounts=$mounts;networks=[pscustomobject]$networks;labels=@{'com.docker.compose.project'='fucheng';'com.docker.compose.service'=$service;'com.docker.compose.project.config_files'=$composePath;'io.fucheng.vpc.managed'='full-v1';'io.fucheng.vpc.deployment'=$deployment.id}}
}
function Assert-UpgradeIdentity([string]$Ref,[string]$ImageId,[bool]$RequireHealthy=$true,[bool]$AllowMixed=$false) {
 if($mode -cin @('compose_missing_backup','compose_foreign_backup','compose_extra_project')){return ,(& $script:realIdentity $Ref $ImageId $RequireHealthy $AllowMixed)}
 if($script:mixed -and !$AllowMixed){throw 'STACK_IDENTITY_MISMATCH'}
 if($mode -eq 'identity'){throw 'STACK_IDENTITY_MISMATCH'}
 $out=@();foreach($n in @('app','backup','cloudflared')){$out+=,[pscustomobject]@{service=$n;id=(@{app='1';backup='2';cloudflared='3'}[$n]*64);name=('fucheng-'+$n);state=$script:states[$n]}}
 return ,$out
}
function Test-DeployPublic {return ($mode -ne 'public')}
function Invoke-VpcChecked([string[]]$Arguments,[int]$Limit=15) {
 $script:calls.Add(@($Arguments));$a=$Arguments
 if($a[0] -eq 'context'){if($mode -eq 'remote'){return 'tcp://evil:2376'};return 'npipe:////./pipe/dockerDesktopLinuxEngine'}
 if($a[0] -eq 'info'){return 'linux|x86_64'}
 if($a[0] -eq 'image'){if($mode -eq 'manifest_store'){return ($a[-1] -split '@')[1]};if($a[-1] -ceq $TargetImage){if($mode -eq 'image'){return 'sha256:'+('0'*64)};return $ExpectedImageId};return $oldImageId}
 if($a[0] -eq 'pull'){return ''}
 if($a[0] -eq 'container' -and '-a' -cin $a){$items=@();foreach($s in @('app','backup','cloudflared')){if($states[$s] -ne 'missing'){$items+=(@{app='1';backup='2';cloudflared='3'}[$s]*64)+'|fucheng-'+$s+'|fucheng'}};if($script:mixed -and $mode -eq 'compose_extra_project'){$items+=('9'*64)+'|unknown|fucheng'};return $items -join "`n"}
 if($a[0] -eq 'container'){if($mode -eq 'writer'){return '9'*64};$items=@();foreach($s in @('app','backup')){if($states[$s] -eq 'running'){$items+=(@{app='1';backup='2'}[$s]*64)}};return $items -join "`n"}
 if($a[0] -eq 'stop'){$s=@{'1'='app';'2'='backup';'3'='cloudflared'}[$a[-1].Substring(0,1)];if($mode -eq 'stop_unknown' -and $s -eq 'cloudflared'){throw 'DOCKER_COMMAND_UNCONFIRMED'};if($mode -ne 'still_running'){$states[$s]='exited'};return ''}
 if($a[0] -eq 'inspect'){
  if($a[-1] -match '^fucheng-(app|backup|cloudflared)$'){$v=$states[$Matches[1]];if(($a -join ' ') -like '*Health*'){return $v+'|healthy'};return $v}
  if($a[-1] -match '^[123]{64}$' -and ($a -join ' ') -like '*mounts*'){return (@{id=$a[-1];mounts=@(@{Type='volume';Name='fucheng_data';RW=$true})}|ConvertTo-Json -Compress)}
  if($a[-1] -match '^[123]{64}$'){if($a[-1] -eq ('9'*64)){return '{"id":"9","mounts":[{"Type":"volume","Name":"fucheng_data","RW":true}]}'};return $states[@{'1'='app';'2'='backup';'3'='cloudflared'}[$a[-1].Substring(0,1)]]}
  if($a[-1] -eq ('9'*64)){return '{"id":"9","mounts":[{"Type":"volume","Name":"fucheng_data","RW":true}]}'}
  return 'exited|0'
 }
 if($a[0] -eq 'create'){
  $op=$journal.operations[-1]
  if($mode -eq 'backup_unknown' -and $op.name -eq 'backup'){throw 'DOCKER_COMMAND_UNCONFIRMED'}
  if($op.name -eq 'backup'){
   $db=Join-Path $checkpointDir 'manual-20261103T000000Z-12345678.db';$media=$db -replace '\.db$','.media.tar'
   [IO.File]::WriteAllText($db,'synthetic db');[IO.File]::WriteAllText($media,'synthetic media')
   $meta=@{file=[IO.Path]::GetFileName($db);sha256=(Get-FileHash $db).Hash.ToLowerInvariant();media_file=[IO.Path]::GetFileName($media);media_sha256=(Get-FileHash $media).Hash.ToLowerInvariant();revision='0015_deployment_diagnostics';integrity='ok';foreign_key_errors=0;restore_config=@{image_ref=$oldImage;public_origin=$origin;base_path='';proxy_kind='cloudflare'}}
   if($mode -eq 'backup_hash'){$meta.sha256='0'*64}
   [IO.File]::WriteAllText(($db -replace '\.db$','.json'),($meta|ConvertTo-Json))
  }
  return (@{backup='4';before='5';after='6'}[$op.name]*64)
 }
 if($a[0] -eq 'start'){return ''}
 if($a[0] -eq 'logs'){
  $digest=if($mode -eq 'data_changed' -and $journal.operations[-1].name -eq 'after'){'d'*64}else{'c'*64}
  return (@{ok=$true;schema='0015_deployment_diagnostics';digest=$digest;admin_count=1;media_digest=('e'*64);integrity_ok=$true;fk_ok=$true}|ConvertTo-Json -Compress)
 }
 if($a[0] -eq 'volume'){return (@{'com.docker.compose.project'='fucheng';'io.fucheng.vpc.managed'='full-v1';'io.fucheng.vpc.deployment'=$deployment.id}|ConvertTo-Json -Compress)}
 if($a[0] -eq 'network'){return (@{internal=$true;ipam=@(@{Subnet='172.30.98.0/24'});containers=@{};labels=@{'io.fucheng.vpc.managed'='full-v1';'io.fucheng.vpc.deployment'=$deployment.id}}|ConvertTo-Json -Depth 8 -Compress)}
 if($a[0] -eq 'compose'){if($mode -cin @('compose_missing_backup','compose_foreign_backup','compose_extra_project')){$states.app='running';$states.backup=$(if($mode -eq 'compose_missing_backup'){'missing'}else{'running'});$script:mixed=$true;throw 'DOCKER_COMMAND_UNCONFIRMED'};if($mode -eq 'compose_unknown'){$states.app='running';$script:mixed=$true;throw 'DOCKER_COMMAND_UNCONFIRMED'};foreach($s in @('app','backup')){$states[$s]='running'};if($a[-1] -eq 'cloudflared'){$states.cloudflared='running'};return ''}
 throw 'UNEXPECTED_DOCKER_ACTION'
}
if($mode -eq 'partial' -or $mode -eq 'complete'){
 $u=Join-Path $r ('backup/upgrade-'+('a'*32));$null=New-Item -ItemType Directory $u
 $j=FixtureReceipt ('a'*32) $oldImage $oldImageId TARGET IMAGEID '8';if($mode -eq 'partial'){$j.phase='BACKUP_PENDING'};$j['previous_upgrade_id']=$prior.id
 [IO.File]::WriteAllText((Join-Path $u 'upgrade-journal.json'),($j|ConvertTo-Json -Depth 10));[IO.File]::WriteAllText((Join-Path $u 'compose.before.yml'),$text);[IO.File]::WriteAllText((Join-Path $u 'owner.before.txt'),('fucheng-vpc-full-v1|'+(Get-VpcHash $text)))
 if($mode -eq 'complete'){$text=$text.Replace($oldImage,TARGET);[IO.File]::WriteAllText((Join-Path $r 'compose.yml'),$text);[IO.File]::WriteAllText((Join-Path $r 'owner.txt'),('fucheng-vpc-full-v1|'+(Get-VpcHash $text)))}
}
$env:DOCKER_HOST='';Invoke-ClubUpgrade TARGET IMAGEID
[IO.File]::WriteAllText(CALLS,(@{calls=$calls.ToArray();states=$states;historical_unchanged=($oldJournal -ceq [IO.File]::ReadAllText((Join-Path $r 'deploy-journal.json')));prior_unchanged=($priorJournal -ceq [IO.File]::ReadAllText((Join-Path $priorDir 'upgrade-journal.json')))}|ConvertTo-Json -Depth 12))
'''
    for k,v in [('MODE',q(mode)),('ROOT',q(root)),('TARGET',q(NEW)),('IMAGEID',q(NEW_ID)),('CALLS',q(calls))]:body=body.replace(k,v)
    r=ps(tmp_path,body)
    assert calls.exists(),r.stdout+r.stderr
    return r,json.loads(calls.read_text()),root

@pytest.mark.parametrize('mode,code',[('acl','PRIVATE_ACL_UNCONFIRMED'),('remote','LOCAL_DOCKER_REQUIRED'),('recipe','UNKNOWN_MANAGED_FILES'),('identity','STACK_IDENTITY_MISMATCH'),('writer','OTHER_TARGET_WRITER'),('image','TARGET_IMAGE_MISMATCH'),('partial','UPGRADE_RECONCILIATION_REQUIRED')])
def test_preflight_failure_preserves_running_stack(tmp_path,mode,code):
    r,s,_=invoke(tmp_path,mode)
    assert 'code='+code in r.stdout,r.stdout+r.stderr
    assert not any(a[0] in ('stop','create','start','compose') for a in s['calls'])
    assert set(s['states'].values())=={'running'}
    assert s['historical_unchanged'] and s['prior_unchanged']

@pytest.mark.parametrize('mode,code',[('backup_unknown','DOCKER_COMMAND_UNCONFIRMED'),('backup_hash','BACKUP_HASH_MISMATCH'),('data_changed','DATA_CHANGED_REVIEW_REQUIRED'),('public','PUBLIC_HEALTH_UNCONFIRMED'),('stop_unknown','DOCKER_COMMAND_UNCONFIRMED'),('still_running','STACK_STOP_UNCONFIRMED')])
def test_failure_keeps_original_operations_and_never_starts_old_stack(tmp_path,mode,code):
    r,s,root=invoke(tmp_path,mode)
    assert 'code='+code in r.stdout,r.stdout+r.stderr
    assert not any(a[0] in ('rm','prune') or '--rm' in a or any(x in a for x in ('init','migrate','restore','import-backup','admin')) for a in s['calls'])
    assert not any(a[0]=='start' and a[-1] in ('1'*64,'2'*64,'3'*64) for a in s['calls'])
    if mode=='backup_unknown':
        j=json.loads(next(p for p in root.glob('backup/upgrade-*/upgrade-journal.json') if p.parent.name!='upgrade-'+'c'*32).read_text())
        assert j['operations'][0]['status']=='create_pending' and j['operations'][0]['id'] is None
        assert len([a for a in s['calls'] if a[0]=='create'])==1
    assert s['historical_unchanged'] and s['prior_unchanged']

def test_complete_rerun_is_read_only(tmp_path):
    r,s,_=invoke(tmp_path,'complete')
    assert 'COMPLETE' in r.stdout,r.stdout+r.stderr
    assert not any(a[0] in ('pull','stop','create','start','compose') for a in s['calls'])
    assert s['historical_unchanged'] and s['prior_unchanged']

def test_success_backup_then_verify_then_switch_then_verify_before_public(tmp_path):
    r,s,root=invoke(tmp_path)
    assert 'COMPLETE' in r.stdout,r.stdout+r.stderr
    j=json.loads(next(p for p in root.glob('backup/upgrade-*/upgrade-journal.json') if p.parent.name!='upgrade-'+'c'*32).read_text())
    assert j['phase']=='COMPLETE'
    assert [o['name'] for o in j['operations']]==['backup','before','after']
    assert all(o['status']=='complete' for o in j['operations'])
    assert [o['id'] for o in j['operations']]==[x*64 for x in '456']
    assert j['previous_upgrade_id']=='c'*32
    assert s['historical_unchanged'] and s['prior_unchanged']
    creates=[a for a in s['calls'] if a[0]=='create']
    assert len(creates)==3 and all('--network' in a and a[a.index('--network')+1]=='none' and '--read-only' in a for a in creates)
    assert 'fucheng_data:/data:ro' in creates[1] and 'fucheng_data:/data:ro' in creates[2]
    assert OLD not in (root/'compose.yml').read_text() and NEW in (root/'compose.yml').read_text()

def test_invalid_pin_and_non_windows_stop_without_docker(tmp_path):
    r=ps(tmp_path,"function Assert-VpcWindows {}\nfunction Invoke-VpcChecked {throw 'MUST_NOT_REACH_DOCKER'}\nInvoke-ClubUpgrade 'latest' 'sha256:bad'")
    assert 'code=TARGET_PIN_REQUIRED' in r.stdout and 'MUST_NOT_REACH_DOCKER' not in r.stdout+r.stderr

def test_summary_covers_admin_credentials_sessions_and_media_without_disclosure(tmp_path):
    import sqlite3,sys,hashlib
    r=ps(tmp_path,'[IO.File]::WriteAllText('+q(tmp_path/'summary.py')+',(Get-UpgradeSummarySource))')
    assert r.returncode==0 and not r.stderr
    data=tmp_path/'data';data.mkdir();(data/'active.json').write_text('{"database":"active.db"}')
    db=sqlite3.connect(data/'active.db')
    db.executescript("CREATE TABLE alembic_version(version_num TEXT); INSERT INTO alembic_version VALUES('0015_deployment_diagnostics'); CREATE TABLE admins(id INTEGER PRIMARY KEY,username TEXT,password_hash TEXT); INSERT INTO admins VALUES(1,'private-admin','DO_NOT_PRINT_HASH'); CREATE TABLE login_sessions(id TEXT); INSERT INTO login_sessions VALUES('DO_NOT_PRINT_SESSION'); CREATE TABLE business(id INTEGER);")
    db.commit();(data/'announcement-media').mkdir();(data/'announcement-media'/'private.jpg').write_bytes(b'synthetic')
    def summary():
        result=subprocess.run([sys.executable,str(tmp_path/'summary.py'),str(data)],capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        for secret in ('private-admin','DO_NOT_PRINT_HASH','DO_NOT_PRINT_SESSION','private.jpg','admins','login_sessions'):assert secret not in result.stdout
        return json.loads(result.stdout)
    first=summary();assert first['admin_count']==1 and first['schema']=='0015_deployment_diagnostics'
    db.execute("UPDATE admins SET password_hash='CHANGED_SECRET'");db.commit();second=summary();assert second['digest']!=first['digest']
    db.execute("DELETE FROM login_sessions");db.commit();third=summary();assert third['digest']!=second['digest']
    (data/'announcement-media'/'private.jpg').write_bytes(b'changed');fourth=summary();assert fourth['media_digest']!=third['media_digest']
    db.close()

@pytest.mark.parametrize('mode',['ok','windows_bind','wrong_image','wrong_volume','public_port','wrong_secret_mount','extra_network','wrong_ip','wrong_labels','foreign_network_member','foreign_project_container','mixed_images','mixed_wrong_image','manifest_images','missing_app_health','known_history','wrong_history_name','running_history'])
def test_real_identity_guard_has_bounded_scope(tmp_path,mode):
    # Exercise actual identity guard; only Docker transport and selected JSON are mocked.
    out=tmp_path/'identity.json'
    body=r'''
$root='C:\Users\club\AppData\Local\Fucheng';$composePath=Join-Path $root 'compose.yml'
# On portable Linux PowerShell Join-Path cannot resolve a Windows drive. The
# actual Windows mount normalization gets its own probe below; fixture here is native.
$root=ROOT;$composePath=Join-Path $root 'compose.yml';$mode=MODE
if($mode -eq 'windows_bind'){$null=New-PSDrive -Name C -PSProvider FileSystem -Root '/tmp';$root='C:\Users\club\AppData\Local\Fucheng';$composePath=[IO.Path]::GetFullPath((Join-Path $root 'compose.yml'))}
$deployment=[pscustomobject]@{id=('e'*32);operations=@(@{id=('4'*64);container='fucheng-op-eeeeeeeeeeee-backup'});old_default=$false};$priorUpgrade=[pscustomobject]@{operations=@(@{id=('5'*64);container=('fucheng-upgrade-'+('c'*32)+'-backup')})};$journal=[pscustomobject]@{operations=@(@{id=('6'*64);container=('fucheng-upgrade-'+('a'*32)+'-before')})};$tunnelImageId='sha256:'+('f'*64)
function Get-UpgradeContainer([string]$Name){
 $service=$Name.Substring(8);$id=@{app='1';backup='2';cloudflared='3'}[$service]*64
 $mounts=@();if($service -ne 'cloudflared'){$mounts+=@{Type='volume';Name='fucheng_data';Destination='/data';RW=$true}}
 $extra=if($service -eq 'app'){@('/run/secrets/turnstile_secret','turnstile.secret',$false)}elseif($service -eq 'backup'){@('/backups','backup/live',$true)}else{@('/run/secrets/tunnel_token','tunnel.token',$false)}
 $mounts+=@{Type='bind';Source=(Join-Path $root $extra[1]);Destination=$extra[0];RW=$extra[2]}
 if($mode -eq 'windows_bind'){$mounts[-1].Source='/run/desktop/mnt/host/c/Users/club/AppData/Local/Fucheng/'+$extra[1]}
 $networks=if($service -eq 'backup'){@{none=@{}}}else{@{fucheng_origin=@{IPAddress=$(if($service -eq 'app'){'172.30.98.2'}else{'172.30.98.3'})};fucheng_default=@{}}}
 $v=@{id=$id;name=('/'+$Name);image=$(if($service -eq 'cloudflared'){$tunnelImageId}else{$oldImageId});ref=$(if($service -eq 'cloudflared'){$tunnelImage}else{$oldImage});state='running';health='healthy';readonly=$true;user='10001:10001';ports=[pscustomobject]@{};network_mode=$(if($service -eq 'backup'){'none'}else{'fucheng_default'});command=$(if($service -eq 'app'){@('serve')}elseif($service -eq 'backup'){@('backup-loop')}else{@('tunnel','--no-autoupdate','--protocol','quic','run','--token-file','/run/secrets/tunnel_token')});mounts=$mounts;networks=[pscustomobject]$networks;labels=@{'com.docker.compose.project'='fucheng';'com.docker.compose.service'=$service;'com.docker.compose.project.config_files'=$composePath;'io.fucheng.vpc.managed'='full-v1';'io.fucheng.vpc.deployment'=$deployment.id}}
 if($service -eq 'cloudflared'){$v.health=$null}
 if($mode -eq 'manifest_images'){$v.image=($v.ref -split '@')[1]}
 if($service -eq 'app'){
  if($mode -cin @('mixed_images','mixed_wrong_image')){$v.ref=NEWREF;$v.image=NEWID;if($mode -eq 'mixed_wrong_image'){$v.image='sha256:'+('0'*64)}}
  switch($mode){
   'missing_app_health' {$v.health=$null}
   'wrong_image' {$v.image='sha256:'+('0'*64)}
   'wrong_volume' {$v.mounts[0].Name='other_data'}
   'public_port' {$v.ports=[pscustomobject]@{'8000/tcp'=@(@{HostIp='0.0.0.0';HostPort='8000'})}}
   'wrong_secret_mount' {$v.mounts[1].Source=Join-Path $root 'other.secret'}
   'extra_network' {$v.networks|Add-Member -NotePropertyName evil -NotePropertyValue @{}}
   'wrong_ip' {$v.networks.fucheng_origin.IPAddress='172.30.98.9'}
   'wrong_labels' {$v.labels.'io.fucheng.vpc.deployment'='0'*32}
  }
 }
 return [pscustomobject]$v
}
function Invoke-VpcChecked([string[]]$Arguments,[int]$Limit=15){
 if($Arguments[0] -eq 'container'){$s=@('1','2','3')|ForEach-Object {($_*64)+'|fucheng-'+@{'1'='app';'2'='backup';'3'='cloudflared'}[$_]+'|fucheng'};if($mode -cin @('known_history','wrong_history_name','running_history')){foreach($n in @('4','5','6')){$name=@{'4'='fucheng-op-eeeeeeeeeeee-backup';'5'=('fucheng-upgrade-'+('c'*32)+'-backup');'6'=('fucheng-upgrade-'+('a'*32)+'-before')}[$n];if($mode -eq 'wrong_history_name' -and $n -eq '5'){$name='fucheng-upgrade-forged'};$s+=($n*64)+'|'+$name+'|fucheng'}};if($mode -eq 'foreign_project_container'){$s+=('9'*64)+'|other|fucheng'};return $s -join "`n"}
 if($Arguments[0] -eq 'inspect'){if($mode -eq 'running_history'){return 'running'};return 'exited'}
 if($Arguments[0] -eq 'volume'){return (@{'com.docker.compose.project'='fucheng';'io.fucheng.vpc.managed'='full-v1';'io.fucheng.vpc.deployment'=$deployment.id}|ConvertTo-Json -Compress)}
 if($Arguments[0] -eq 'network'){$members=@{};if($mode -eq 'foreign_network_member'){$members[('9'*64)]=@{}};return (@{internal=$true;ipam=@(@{Subnet='172.30.98.0/24'});containers=$members;labels=@{'io.fucheng.vpc.managed'='full-v1';'io.fucheng.vpc.deployment'=$deployment.id}}|ConvertTo-Json -Depth 8 -Compress)}
 throw 'UNEXPECTED_DOCKER_ACTION'
}
try{if($mode -cin @('mixed_images','mixed_wrong_image')){$v=Assert-UpgradeIdentity NEWREF NEWID $false $true}else{$v=Assert-UpgradeIdentity $oldImage $oldImageId $true};[IO.File]::WriteAllText(OUT,'ok:'+@($v).Count)}catch{[IO.File]::WriteAllText(OUT,$_.Exception.Message)}
'''
    # remove the intentionally explained Windows path declaration in Linux fixture
    body=body.replace("$root='C:\\Users\\club\\AppData\\Local\\Fucheng';$composePath=Join-Path $root 'compose.yml'",'',1)
    for k,v in [('ROOT',q(tmp_path/'root')),('MODE',q(mode)),('OUT',q(out)),('NEWREF',q(NEW)),('NEWID',q(NEW_ID))]:body=body.replace(k,v)
    r=ps(tmp_path,body)
    assert out.exists(),r.stdout+r.stderr
    result=out.read_text()
    if mode in ('ok','windows_bind','mixed_images','manifest_images','known_history'):assert result=='ok:3',result
    elif mode=='missing_app_health':assert result=='STACK_UNHEALTHY',result
    elif mode in ('foreign_network_member','foreign_project_container','wrong_history_name','running_history'):assert result=='UNKNOWN_FUCHENG_RESOURCE',result
    else:assert result=='STACK_IDENTITY_MISMATCH',result


def test_partial_compose_timeout_stops_verified_mixed_old_new_stack(tmp_path):
    r,s,root=invoke(tmp_path,'compose_unknown')
    assert 'code=DOCKER_COMMAND_UNCONFIRMED' in r.stdout,r.stdout+r.stderr
    assert set(s['states'].values())=={'exited'},'Known new app must not remain writing after partial Compose up'
    assert not any(a[0]=='start' and a[-1] in ('1'*64,'2'*64,'3'*64) for a in s['calls'])
    j=json.loads(next(p for p in root.glob('backup/upgrade-*/upgrade-journal.json') if p.parent.name!='upgrade-'+'c'*32).read_text())
    assert j['stop_confirmed'] is True


def test_manifest_store_journal_and_images_complete_without_rewriting_history(tmp_path):
    r,s,root=invoke(tmp_path,'manifest_store')
    assert 'COMPLETE' in r.stdout,r.stdout+r.stderr
    assert s['historical_unchanged'] and s['prior_unchanged']
    j=json.loads(next(p for p in root.glob('backup/upgrade-*/upgrade-journal.json') if p.parent.name!='upgrade-'+'c'*32).read_text())
    assert j['phase']=='COMPLETE' and j['target_image_id']==NEW_ID

@pytest.mark.parametrize('actual,allowed',[('config',True),('manifest',True),('other',False)])
def test_digest_identity_accepts_only_fixed_config_or_manifest(tmp_path,actual,allowed):
    v={'config':OLD_ID,'manifest':OLD.split('@')[1],'other':'sha256:'+'0'*64}[actual]
    r=ps(tmp_path,'Write-Output (Test-UpgradeImageIdentity '+q(v)+' '+q(OLD)+' '+q(OLD_ID)+')')
    assert r.returncode==0 and r.stdout.strip()==str(allowed),r.stdout+r.stderr


def test_real_docker_optional_health_template():
    import re,shutil
    name=os.environ.get('FUCHENG_TEST_HEALTHLESS_CONTAINER')
    if not name:
        pytest.skip('Set isolated healthless container for real Docker template regression')
    source=SCRIPT.read_text(encoding='utf-8-sig')
    function=source.split('function Get-UpgradeContainer',1)[1].split('function Assert-UpgradeIdentity',1)[0]
    template=re.search(r"\$format='([^']+)'",function).group(1)
    command=['docker','--context',os.environ.get('FUCHENG_TEST_DOCKER_CONTEXT','default'),'inspect','--type','container','--format',template,name]
    result=subprocess.run(command,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    value=json.loads(result.stdout)
    assert value['health'] is None and value['state']=='created'


@pytest.mark.parametrize('command,visible',[("@('inspect','--type')",True),("@('compose','up')",False)])
def test_docker_failure_reports_command_but_only_read_metadata_stderr(tmp_path,command,visible):
    body="function Invoke-ProbeDocker {return @{exit_code=1;timed_out=$false;stdout='';stderr='SYNTHETIC_ERROR_DETAIL'}}\ntry {Invoke-VpcChecked "+command+"} catch {}"
    r=ps(tmp_path,body)
    assert 'DOCKER_FAILED:' in r.stdout
    assert ('SYNTHETIC_ERROR_DETAIL' in r.stdout)==visible

@pytest.mark.parametrize('mode,code',[('source_drift','JOURNAL_INVALID'),('receipt_digest','PRESERVATION_NOT_CONFIRMED'),('prior_partial','UPGRADE_RECONCILIATION_REQUIRED'),('prior_operation','JOURNAL_INVALID'),('prior_deployment','JOURNAL_INVALID'),('prior_next','JOURNAL_UPDATE_PENDING'),('compose_next','JOURNAL_UPDATE_PENDING'),('unknown_upgrade','UPGRADE_RECONCILIATION_REQUIRED'),('multiple_prior','UPGRADE_RECONCILIATION_REQUIRED')])
def test_chain_rejection_never_changes_running_stack(tmp_path,mode,code):
    r,s,_=invoke(tmp_path,mode)
    assert 'code='+code in r.stdout,r.stdout+r.stderr
    assert not any(a[0] in ('pull','stop','create','start','compose') for a in s['calls'])
    assert set(s['states'].values())=={'running'}
    assert s['historical_unchanged'] and s['prior_unchanged']


def test_pre_13_image_cannot_be_used_as_upgrade_target(tmp_path):
    r=ps(tmp_path,"function Assert-VpcWindows {}\nfunction Get-UpgradeRoot {throw 'MUST_NOT_READ_DEPLOYMENT'}\nInvoke-ClubUpgrade $originalImage $originalImageId")
    assert 'code=TARGET_PIN_REQUIRED' in r.stdout,r.stdout+r.stderr


@pytest.mark.parametrize('mode', ['compose_missing_backup','compose_foreign_backup'])
def test_failed_partial_stack_stops_known_app_when_other_member_is_missing_or_foreign(tmp_path, mode):
    # Actual per-container identity guard; only Docker transport/JSON are fixtures.
    r,s,root=invoke(tmp_path,mode)
    assert 'code=DOCKER_COMMAND_UNCONFIRMED' in r.stdout,r.stdout+r.stderr
    assert s['states']['app']=='exited', 'Known target app must stop even when backup inspection fails'
    assert s['states']['cloudflared']=='exited'
    assert s['states']['backup']==('missing' if mode=='compose_missing_backup' else 'running')
    j=json.loads(next(p for p in root.glob('backup/upgrade-*/upgrade-journal.json') if p.parent.name!='upgrade-'+'c'*32).read_text())
    assert j['stop_confirmed'] is False
    assert j['failure_code']=='DOCKER_COMMAND_UNCONFIRMED'
    # Initial coordinated stop is allowed; cleanup must not stop the foreign/missing backup.
    stops=[a[-1] for a in s['calls'] if a[0]=='stop']
    assert stops.count('1'*64)==2 and stops.count('2'*64)==1
    assert not any(a[0]=='start' and a[-1] in ('1'*64,'2'*64,'3'*64) for a in s['calls'])
    assert s['historical_unchanged'] and s['prior_unchanged']


def test_cleanup_preserves_global_unknown_resource_failure_after_stopping_known_writers(tmp_path):
    r,s,root=invoke(tmp_path,'compose_extra_project')
    assert 'code=DOCKER_COMMAND_UNCONFIRMED' in r.stdout,r.stdout+r.stderr
    assert set(s['states'].values())=={'exited'}
    j=json.loads(next(p for p in root.glob('backup/upgrade-*/upgrade-journal.json') if p.parent.name!='upgrade-'+'c'*32).read_text())
    assert j['stop_confirmed'] is False
    assert not any(a[0]=='stop' and a[-1]=='9'*64 for a in s['calls'])
