"""Focused offline regressions; no Docker daemon or Windows host is touched."""
import json, os, subprocess
from pathlib import Path
import pytest

HERE=Path(__file__).resolve().parents[1]
SCRIPT=HERE/'deploy/docker/club-vpc-upgrade.ps1'
PWSH=Path(os.environ.get('FUCHENG_TEST_PWSH','pwsh'))
if not __import__('shutil').which(str(PWSH)):
    pytest.skip('PowerShell runtime is not configured', allow_module_level=True)
OLD='momonong/fucheng-players-system@sha256:0e5a297b0d16876fa56e1b9bed0470c3b8632d55ded6b23ffc5c18315f39e6e2'
OLD_ID='sha256:2cfa6229bc207b1df68aac4ef94baadb8a5b8bf149f536f1e3f3ee45d0403034'
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
$old=[pscustomobject]@{version=1;phase='COMPLETE';id=$jid;source_id=('f'*64);image_id=$oldImageId;target_volume='fucheng_data';old_default=$false;verification=@{business_match=$true;admin_match=$true;media_match=$true};operations=@()}
if($mode -eq 'manifest_store'){$old.image_id=($oldImage -split '@')[1]}
$text=Get-DeployCompose $jid $false
foreach($name in @('setup.lock','protected.env','turnstile.secret','tunnel.token')){[IO.File]::WriteAllText((Join-Path $r $name),'DO_NOT_READ_SECRET')}
[IO.File]::WriteAllText((Join-Path $r 'compose.yml'),$text)
[IO.File]::WriteAllText((Join-Path $r 'owner.txt'),('fucheng-vpc-full-v1|'+(Get-VpcHash $text)))
[IO.File]::WriteAllText((Join-Path $r 'deploy-journal.json'),($old|ConvertTo-Json -Depth 8))
$script:oldJournal=[IO.File]::ReadAllText((Join-Path $r 'deploy-journal.json'))
if($mode -eq 'recipe'){[IO.File]::AppendAllText((Join-Path $r 'compose.yml'),'DRIFT')}
$script:states=@{app='running';backup='running';cloudflared='running'}
function Assert-UpgradeIdentity([string]$Ref,[string]$ImageId,[bool]$RequireHealthy=$true,[bool]$AllowMixed=$false) {
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
 if($a[0] -eq 'container'){if($mode -eq 'writer'){return '9'*64};$items=@();foreach($s in @('app','backup')){if($states[$s] -eq 'running'){$items+=(@{app='1';backup='2'}[$s]*64)}};return $items -join "`n"}
 if($a[0] -eq 'stop'){$s=@{'1'='app';'2'='backup';'3'='cloudflared'}[$a[-1].Substring(0,1)];if($mode -eq 'stop_unknown' -and $s -eq 'cloudflared'){throw 'DOCKER_COMMAND_UNCONFIRMED'};if($mode -ne 'still_running'){$states[$s]='exited'};return ''}
 if($a[0] -eq 'inspect'){
  if($a[-1] -match '^fucheng-(app|backup|cloudflared)$'){$v=$states[$Matches[1]];if(($a -join ' ') -like '*Health*'){return $v+'|healthy'};return $v}
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
  return '4'*64
 }
 if($a[0] -eq 'start'){return ''}
 if($a[0] -eq 'logs'){
  $digest=if($mode -eq 'data_changed' -and $journal.operations[-1].name -eq 'after'){'d'*64}else{'c'*64}
  return (@{ok=$true;schema='0015_deployment_diagnostics';digest=$digest;admin_count=1;media_digest=('e'*64);integrity_ok=$true;fk_ok=$true}|ConvertTo-Json -Compress)
 }
 if($a[0] -eq 'compose'){if($mode -eq 'compose_unknown'){$states.app='running';$script:mixed=$true;throw 'DOCKER_COMMAND_UNCONFIRMED'};foreach($s in @('app','backup')){$states[$s]='running'};if($a[-1] -eq 'cloudflared'){$states.cloudflared='running'};return ''}
 throw 'UNEXPECTED_DOCKER_ACTION'
}
if($mode -eq 'partial' -or $mode -eq 'complete'){
 $u=Join-Path $r ('backup/upgrade-'+('a'*32));$null=New-Item -ItemType Directory $u
 $j=@{version=1;id=('a'*32);deployment_id=$jid;phase=$(if($mode -eq 'complete'){'COMPLETE'}else{'BACKUP_PENDING'});target_image=TARGET;target_image_id=IMAGEID;old_image=$oldImage;old_image_id=$oldImageId;operations=@();failure_code=$null}
 [IO.File]::WriteAllText((Join-Path $u 'upgrade-journal.json'),($j|ConvertTo-Json -Depth 8))
 if($mode -eq 'complete'){$text=$text.Replace($oldImage,TARGET);[IO.File]::WriteAllText((Join-Path $r 'compose.yml'),$text);[IO.File]::WriteAllText((Join-Path $r 'owner.txt'),('fucheng-vpc-full-v1|'+(Get-VpcHash $text)))}
}
$env:DOCKER_HOST='';Invoke-ClubUpgrade TARGET IMAGEID
[IO.File]::WriteAllText(CALLS,(@{calls=$calls.ToArray();states=$states;historical_unchanged=($oldJournal -ceq [IO.File]::ReadAllText((Join-Path $r 'deploy-journal.json')))}|ConvertTo-Json -Depth 12))
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
    assert s['historical_unchanged']

@pytest.mark.parametrize('mode,code',[('backup_unknown','DOCKER_COMMAND_UNCONFIRMED'),('backup_hash','BACKUP_HASH_MISMATCH'),('data_changed','DATA_CHANGED_REVIEW_REQUIRED'),('public','PUBLIC_HEALTH_UNCONFIRMED'),('stop_unknown','DOCKER_COMMAND_UNCONFIRMED'),('still_running','STACK_STOP_UNCONFIRMED')])
def test_failure_keeps_original_operations_and_never_starts_old_stack(tmp_path,mode,code):
    r,s,root=invoke(tmp_path,mode)
    assert 'code='+code in r.stdout,r.stdout+r.stderr
    assert not any(a[0] in ('rm','prune') or '--rm' in a or any(x in a for x in ('init','migrate','restore','import-backup','admin')) for a in s['calls'])
    assert not any(a[0]=='start' and a[-1] in ('1'*64,'2'*64,'3'*64) for a in s['calls'])
    if mode=='backup_unknown':
        j=json.loads(next(root.glob('backup/upgrade-*/upgrade-journal.json')).read_text())
        assert j['operations'][0]['status']=='create_pending' and j['operations'][0]['id'] is None
        assert len([a for a in s['calls'] if a[0]=='create'])==1
    assert s['historical_unchanged']

def test_complete_rerun_is_read_only(tmp_path):
    r,s,_=invoke(tmp_path,'complete')
    assert 'COMPLETE' in r.stdout,r.stdout+r.stderr
    assert not any(a[0] in ('pull','stop','create','start','compose') for a in s['calls'])
    assert s['historical_unchanged']

def test_success_backup_then_verify_then_switch_then_verify_before_public(tmp_path):
    r,s,root=invoke(tmp_path)
    assert 'COMPLETE' in r.stdout,r.stdout+r.stderr
    j=json.loads(next(root.glob('backup/upgrade-*/upgrade-journal.json')).read_text())
    assert j['phase']=='COMPLETE'
    assert [o['name'] for o in j['operations']]==['backup','before','after']
    assert all(o['status']=='complete' and o['id']=='4'*64 for o in j['operations'])
    assert s['historical_unchanged']
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

@pytest.mark.parametrize('mode',['ok','windows_bind','wrong_image','wrong_volume','public_port','wrong_secret_mount','extra_network','wrong_ip','wrong_labels','foreign_network_member','foreign_project_container','mixed_images','mixed_wrong_image','manifest_images','missing_app_health'])
def test_real_identity_guard_has_bounded_scope(tmp_path,mode):
    # Exercise actual identity guard; only Docker transport and selected JSON are mocked.
    out=tmp_path/'identity.json'
    body=r'''
$root='C:\Users\club\AppData\Local\Fucheng';$composePath=Join-Path $root 'compose.yml'
# On portable Linux PowerShell Join-Path cannot resolve a Windows drive. The
# actual Windows mount normalization gets its own probe below; fixture here is native.
$root=ROOT;$composePath=Join-Path $root 'compose.yml';$mode=MODE
if($mode -eq 'windows_bind'){$null=New-PSDrive -Name C -PSProvider FileSystem -Root '/tmp';$root='C:\Users\club\AppData\Local\Fucheng';$composePath=[IO.Path]::GetFullPath((Join-Path $root 'compose.yml'))}
$deployment=[pscustomobject]@{id=('e'*32);operations=@();old_default=$false};$journal=$null;$tunnelImageId='sha256:'+('f'*64)
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
 if($Arguments[0] -eq 'container'){$s=@('1','2','3')|ForEach-Object {($_*64)+'|fucheng-'+@{'1'='app';'2'='backup';'3'='cloudflared'}[$_]+'|fucheng'};if($mode -eq 'foreign_project_container'){$s+=('9'*64)+'|other|fucheng'};return $s -join "`n"}
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
    if mode in ('ok','windows_bind','mixed_images','manifest_images'):assert result=='ok:3',result
    elif mode=='missing_app_health':assert result=='STACK_UNHEALTHY',result
    elif mode in ('foreign_network_member','foreign_project_container'):assert result=='UNKNOWN_FUCHENG_RESOURCE',result
    else:assert result=='STACK_IDENTITY_MISMATCH',result


def test_partial_compose_timeout_stops_verified_mixed_old_new_stack(tmp_path):
    r,s,root=invoke(tmp_path,'compose_unknown')
    assert 'code=DOCKER_COMMAND_UNCONFIRMED' in r.stdout,r.stdout+r.stderr
    assert set(s['states'].values())=={'exited'},'Known new app must not remain writing after partial Compose up'
    assert not any(a[0]=='start' and a[-1] in ('1'*64,'2'*64,'3'*64) for a in s['calls'])
    j=json.loads(next(root.glob('backup/upgrade-*/upgrade-journal.json')).read_text())
    assert j['stop_confirmed'] is True


def test_manifest_store_journal_and_images_complete_without_rewriting_history(tmp_path):
    r,s,root=invoke(tmp_path,'manifest_store')
    assert 'COMPLETE' in r.stdout,r.stdout+r.stderr
    assert s['historical_unchanged']
    j=json.loads(next(root.glob('backup/upgrade-*/upgrade-journal.json')).read_text())
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
