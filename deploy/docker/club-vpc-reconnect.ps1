& {
# 府城修復 v2：核對 Windows 私有 ACL，沿用既有容器；不匯入、不還原。
$ErrorActionPreference='Stop';$utf8=New-Object Text.UTF8Encoding($false)
$appImage='momonong/fucheng-players-system@sha256:0e5a297b0d16876fa56e1b9bed0470c3b8632d55ded6b23ffc5c18315f39e6e2'
$tunnelImage='cloudflare/cloudflared@sha256:faa8e0a1475f137c910be6025f43c8e4092fdd35461b31e19fd1390657a1ff39'
$tunnelId='fa458cdb-0bf4-43a2-89ef-e9d15b348d14';$origin='https://fucheng.momonong.workers.dev'
function Stop-OwnedProcessTree([Diagnostics.Process]$Process) {
    # Only the process object started by this tool is eligible; never use names.
    $killer = $null
    try {
        if ($Process.HasExited) { return $false }
        if ($env:OS -eq 'Windows_NT') {
            $info = New-Object Diagnostics.ProcessStartInfo
            $info.FileName = Join-Path ([Environment]::SystemDirectory) 'taskkill.exe'
            $info.Arguments = '/PID ' + $Process.Id + ' /T /F'
            $info.UseShellExecute = $false
            $info.CreateNoWindow = $true
            $info.RedirectStandardOutput = $true
            $info.RedirectStandardError = $true
            $killer = New-Object Diagnostics.Process
            $killer.StartInfo = $info
            [void]$killer.Start()
            $null = $killer.StandardOutput.ReadToEndAsync()
            $null = $killer.StandardError.ReadToEndAsync()
            if (!$killer.WaitForExit(1000)) {
                try { $killer.Kill() } catch {}
                return $false
            }
            if ($killer.ExitCode -ne 0) { return $false }
        } else {
            # Portable PowerShell 7 test runtime supports this process-tree API.
            $Process.Kill($true)
        }
        return $Process.WaitForExit(1000)
    } catch { return $false }
    finally { if ($killer) { $killer.Dispose() } }
}

function Quote-ProbeArgument([string]$Value) {
 # CommandLineToArgvW quoting, also accepted by portable PowerShell test runtime.
 return '"'+[regex]::Replace([regex]::Replace($Value,'(\\*)"','$1$1\"'),'(\\+)$','$1$1')+'"'
}

function Invoke-ProbeDocker([string[]]$Arguments,[int]$Limit=10) {
 if(!$docker -or !(Test-Path -LiteralPath $docker -PathType Leaf)){return @{exit_code=$null;timed_out=$false;stdout='';stderr=''}}
 $info=New-Object Diagnostics.ProcessStartInfo;$info.FileName=$docker
 $info.Arguments=($Arguments|ForEach-Object {Quote-ProbeArgument $_}) -join ' '
 $info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
 $info.StandardOutputEncoding=[Text.Encoding]::UTF8;$info.StandardErrorEncoding=[Text.Encoding]::UTF8
 $process=New-Object Diagnostics.Process;$process.StartInfo=$info
 try{
  [void]$process.Start();$out=$process.StandardOutput.ReadToEndAsync();$err=$process.StandardError.ReadToEndAsync()
  if(!$process.WaitForExit($Limit*1000)){$null=Stop-OwnedProcessTree $process;return @{exit_code=$null;timed_out=$true;stdout='';stderr=''}}
  if(!$out.Wait(1000) -or !$err.Wait(1000)){return @{exit_code=$null;timed_out=$true;stdout='';stderr=''}}
  return @{exit_code=$process.ExitCode;timed_out=$false;stdout=$out.Result.Trim();stderr=$err.Result.Trim()}
 }catch{return @{exit_code=$null;timed_out=$false;stdout='';stderr=''}}finally{try{if(!$process.HasExited){$null=Stop-OwnedProcessTree $process}}catch{};$process.Dispose()}
}

function Assert-VpcWindows {if($env:OS -cne 'Windows_NT' -or $Host.Name -eq 'Windows PowerShell ISE Host'){throw 'WINDOWS_CONSOLE_REQUIRED'}}

function Assert-VpcNoLink([string]$Path) {
 $current=[IO.Path]::GetFullPath($Path);while($current){if((Test-Path -LiteralPath $current) -and ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'LINKED_PATH'};$parent=[IO.Path]::GetDirectoryName($current);if($parent -ceq $current){break};$current=$parent}
}

function Get-VpcCallerSid {
 return [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
}

function Get-VpcAclSnapshot([string]$Path) {
 $acl=Get-Acl -LiteralPath $Path -ErrorAction Stop
 $rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])|ForEach-Object {
  [pscustomobject]@{sid=$_.IdentityReference.Value;allow=($_.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow)}
 })
 return [pscustomobject]@{owner=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value;protected=[bool]$acl.AreAccessRulesProtected;rules=$rules}
}

function Test-VpcPrivateAcl($Snapshot,[string]$CallerSid,[bool]$IsRoot) {
 if(!$CallerSid -or $Snapshot.owner -isnot [string] -or $Snapshot.protected -isnot [bool]){return $false}
 $trusted=@($CallerSid,'S-1-5-18','S-1-5-32-544')
 if($Snapshot.owner -cnotin $trusted -or ($IsRoot -and !$Snapshot.protected)){return $false}
 $callerAllowed=$false
 foreach($rule in @($Snapshot.rules)){
  if($rule.sid -isnot [string] -or $rule.allow -isnot [bool]){return $false}
  if($rule.allow){if($rule.sid -cnotin $trusted){return $false};if($rule.sid -ceq $CallerSid){$callerAllowed=$true}}
 }
 return $callerAllowed
}

function Assert-VpcOwner([string]$Path) {
 $caller=Get-VpcCallerSid;$snapshot=Get-VpcAclSnapshot $Path
 $ownerClass=if($snapshot.owner -ceq $caller){'目前使用者'}elseif($snapshot.owner -ceq 'S-1-5-18'){'SYSTEM'}elseif($snapshot.owner -ceq 'S-1-5-32-544'){'Administrators'}else{'其他'}
 $private=Test-VpcPrivateAcl $snapshot $caller ($Path -ieq $root)
 Write-Host ('權限核對：'+[IO.Path]::GetFileName($Path)+'；owner='+$ownerClass+'；private_acl='+$private)
 if(!$private){throw 'PRIVATE_ACL_UNCONFIRMED'}
}

function Get-VpcHash([string]$Text) {$sha=[Security.Cryptography.SHA256]::Create();try{return ([BitConverter]::ToString($sha.ComputeHash($utf8.GetBytes($Text)))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}}

function Invoke-VpcChecked([string[]]$Arguments,[int]$Limit=15) {$r=Invoke-ProbeDocker $Arguments $Limit;if($r.timed_out -or $r.exit_code -ne 0){throw 'DOCKER_COMMAND_UNCONFIRMED'};return $r.stdout}

function Get-DeployVerifierSource {
 $sourceText=@'
import hashlib,json,sqlite3,sys
from pathlib import Path
from contextlib import closing
source=Path(sys.argv[1] if len(sys.argv)>1 else '/source');target=Path(sys.argv[2] if len(sys.argv)>2 else '/target')
def database(root):
 p=json.loads((root/'active.json').read_text())['database']
 if not isinstance(p,str) or Path(p).name!=p or not p.endswith('.db'):raise ValueError()
 return sqlite3.connect((root/p).as_uri()+'?mode=ro',uri=True,timeout=10)
def rows(db,table):
 q='"'+table.replace('"','""')+'"'
 values=[json.dumps(row,ensure_ascii=True,separators=(',',':'),default=lambda b:{'bytes':b.hex()}) for row in db.execute('SELECT * FROM '+q)]
 return hashlib.sha256('\n'.join(sorted(values)).encode()).digest(),len(values)
def media(root):
 d=root/'announcement-media'
 if not d.exists():return {}
 files={}
 for p in d.iterdir():
  if p.is_symlink() or not p.is_file():raise ValueError()
  files[p.name]=hashlib.sha256(p.read_bytes()).digest()
 return files
try:
 with closing(database(source)) as a,closing(database(target)) as b:
  for db in (a,b):db.execute('PRAGMA query_only=ON')
  tables=lambda db:db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
  schema=tables(a)==tables(b)
  integrity=all(db.execute('PRAGMA integrity_check').fetchall()==[('ok',)] for db in (a,b))
  fk=all(not db.execute('PRAGMA foreign_key_check').fetchall() for db in (a,b))
  revision=all(db.execute('SELECT version_num FROM alembic_version').fetchall()==[('0015_deployment_diagnostics',)] for db in (a,b))
  business=schema and all(rows(a,name)==rows(b,name) for name,_ in tables(a) if name!='login_sessions')
  admin_a,count_a=rows(a,'admins');admin_b,count_b=rows(b,'admins')
  sessions=b.execute('SELECT count(*) FROM login_sessions').fetchone()[0]==0
  result={'schema':'0015_deployment_diagnostics','schema_match':schema,'integrity_ok':integrity,'fk_ok':fk,'revision_match':revision,'business_match':business,'admin_match':admin_a==admin_b,'source_admin_count':count_a,'target_admin_count':count_b,'target_sessions_zero':sessions,'media_match':media(source)==media(target),'source_preview_marked':(source/'local-http-synthetic.json').is_file(),'target_preview_unmarked':not (target/'local-http-synthetic.json').exists()}
  result['ok']=all(result[k] for k in ('schema_match','integrity_ok','fk_ok','revision_match','business_match','admin_match','target_sessions_zero','media_match','source_preview_marked','target_preview_unmarked')) and count_a>0 and count_a==count_b
 print(json.dumps(result,separators=(',',':')))
except Exception:
 print(json.dumps({'ok':False,'error':'READ_ONLY_VERIFY_FAILED'},separators=(',',':')))
'@
 return $sourceText.Replace("`r`n","`n")
}

function Get-DeployCompose([string]$Id,[bool]$ExistingDefault) {
 $text=@'
name: fucheng
x-runtime: &runtime
  image: APP_IMAGE
  pull_policy: never
  platform: linux/amd64
  user: "10001:10001"
  read_only: true
  tmpfs: ["/tmp:size=16m,mode=1777"]
  cap_drop: [ALL]
  security_opt: [no-new-privileges:true]
  volumes: ["data:/data"]
  labels: {io.fucheng.vpc.managed: full-v1, io.fucheng.vpc.deployment: DEPLOY_ID}
  logging: {driver: json-file, options: {max-size: "5m", max-file: "2"}}
x-ops-env: &ops-env
  FUCHENG_IMAGE_REF: APP_IMAGE
  FUCHENG_BASE_PATH: ""
  FUCHENG_BACKUP_KEEP: "8"
  FUCHENG_RESTORE_PUBLIC_ORIGIN: https://fucheng.momonong.workers.dev
  FUCHENG_RESTORE_PROXY_KIND: cloudflare
services:
  app:
    <<: *runtime
    container_name: fucheng-app
    command: [serve]
    restart: unless-stopped
    stop_grace_period: 45s
    environment:
      <<: *ops-env
      FUCHENG_PUBLIC_ORIGIN: https://fucheng.momonong.workers.dev
      FUCHENG_PROXY_KIND: cloudflare
      FUCHENG_TRUSTED_PROXY: 172.30.98.3
      FUCHENG_COOKIE_SECURE: "true"
      FUCHENG_LOCAL_HTTP_PREVIEW: "false"
      FUCHENG_TURNSTILE_MODE: enabled
      FUCHENG_TURNSTILE_HOSTNAME: fucheng.momonong.workers.dev
      FUCHENG_TURNSTILE_SITEKEY: ${FUCHENG_TURNSTILE_SITEKEY:?Set protected sitekey}
      FUCHENG_TURNSTILE_SECRET_FILE: /run/secrets/turnstile_secret
      FUCHENG_REPORT_SEND_ENABLED: "false"
      FUCHENG_REPORT_UPLOAD_ENABLED: "false"
      FUCHENG_BACKUP_STATUS_FILE: /data/backup-status.json
    secrets: [turnstile_secret]
    networks: {origin: {ipv4_address: 172.30.98.2}, default: {}}
  backup:
    <<: *runtime
    container_name: fucheng-backup
    command: [backup-loop]
    restart: unless-stopped
    environment: *ops-env
    network_mode: none
    volumes: ["data:/data", "./backup/live:/backups"]
    depends_on: {app: {condition: service_healthy}}
    healthcheck:
      test: [CMD, python, /app/runtime.py, backup-health]
      interval: 30s
      timeout: 10s
      start_period: 30s
      retries: 3
  cloudflared:
    image: TUNNEL_IMAGE
    pull_policy: never
    platform: linux/amd64
    container_name: fucheng-cloudflared
    command: [tunnel, --no-autoupdate, --protocol, quic, run, --token-file, /run/secrets/tunnel_token]
    restart: unless-stopped
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    secrets: [tunnel_token]
    networks: {origin: {ipv4_address: 172.30.98.3}, default: {}}
    depends_on: {app: {condition: service_healthy}, backup: {condition: service_healthy}}
    labels: {io.fucheng.vpc.managed: full-v1, io.fucheng.vpc.deployment: DEPLOY_ID}
    logging: {driver: json-file, options: {max-size: "1m", max-file: "2"}}
volumes:
  data: {external: true, name: fucheng_data}
networks:
  origin:
    internal: true
    ipam: {config: [{subnet: 172.30.98.0/24}]}
    labels: {io.fucheng.vpc.managed: full-v1, io.fucheng.vpc.deployment: DEPLOY_ID}
  default:
DEFAULT_NETWORK
secrets:
  tunnel_token: {file: ./tunnel.token}
  turnstile_secret: {file: ./turnstile.secret}
'@
 $network=if($ExistingDefault){'    external: true' + "`n"+'    name: fucheng_default'}else{'    labels: {io.fucheng.vpc.managed: full-v1, io.fucheng.vpc.deployment: DEPLOY_ID}'}
 return $text.Replace('DEFAULT_NETWORK',$network).Replace('APP_IMAGE',$appImage).Replace('TUNNEL_IMAGE',$tunnelImage).Replace('DEPLOY_ID',$Id).Replace("`r`n","`n")
}

function Get-DeploySource {
 $format='{"id":{{json .Id}},"image":{{json .Image}},"state":{{json .State.Status}},"env":{{json .Config.Env}},"mounts":{{json .Mounts}},"ports":{{json .HostConfig.PortBindings}},"command":{{json .Config.Cmd}}}'
 $v=(Invoke-VpcChecked @('inspect','--type','container','--format',$format,'fucheng-check-v120'))|ConvertFrom-Json
 if($v.id -cnotmatch '^[a-f0-9]{64}$' -or $v.image -cne $appImageId -or $v.state -cnotin @('running','exited') -or ($v.command -join '|') -cne 'serve'){throw 'SOURCE_IDENTITY_MISMATCH'}
 if(@($v.mounts).Count -ne 1 -or $v.mounts[0].Type -cne 'volume' -or $v.mounts[0].Name -cne 'fucheng-check-v120_data' -or $v.mounts[0].Destination -cne '/data' -or !$v.mounts[0].RW){throw 'SOURCE_VOLUME_MISMATCH'}
 foreach($expected in @('FUCHENG_LOCAL_HTTP_PREVIEW=true','FUCHENG_PUBLIC_ORIGIN=http://localhost:8052','FUCHENG_COOKIE_SECURE=false','FUCHENG_PROXY_KIND=local')){if($expected -cnotin $v.env){throw 'SOURCE_PREVIEW_MISMATCH'}}
 foreach($entry in $v.env){if($entry -cmatch '^FUCHENG_(BASE_PATH|TRUSTED_PROXY)=(.+)$'){throw 'SOURCE_PREVIEW_MISMATCH'}}
 $portNames=@($v.ports.PSObject.Properties.Name);if($portNames.Count -ne 1 -or $portNames[0] -cne '8000/tcp'){throw 'SOURCE_PORT_MISMATCH'};foreach($binding in $v.ports.'8000/tcp'){if($binding.HostIp -cnotin @('127.0.0.1','::1') -or $binding.HostPort -cne '8052'){throw 'SOURCE_PORT_MISMATCH'}}
 return $v
}

function Assert-DeployNoWriter([string]$Allowed='') {
 $ids=Invoke-VpcChecked @('container','ls','--quiet','--no-trunc','--filter','volume=fucheng-check-v120_data');foreach($id in @($ids -split "`r?`n"|Where-Object {$_})){
  $v=(Invoke-VpcChecked @('inspect','--type','container','--format','{"id":{{json .Id}},"mounts":{{json .Mounts}}}',$id))|ConvertFrom-Json
  if($v.id -ceq $Allowed){continue};foreach($mount in $v.mounts){if($mount.Type -ceq 'volume' -and $mount.Name -ceq 'fucheng-check-v120_data' -and $mount.RW){throw 'OTHER_SOURCE_WRITER'}}
 }
}

function Get-DeployResources([string]$DeploymentId='', [bool]$AllowOld=$false) {
 $found=@{containers=@();networks=@();volumes=@()}
 foreach($kind in @('container','network','volume')){
  $format=if($kind -eq 'container'){'{{.ID}}|{{.Names}}|{{.Label "com.docker.compose.project"}}|{{.Label "io.fucheng.vpc.managed"}}|{{.Label "io.fucheng.vpc.deployment"}}|{{.Label "com.docker.compose.project.config_files"}}|{{.Label "com.docker.compose.service"}}'}elseif($kind -eq 'network'){'{{.ID}}|{{.Name}}|{{.Label "com.docker.compose.project"}}|{{.Label "io.fucheng.vpc.managed"}}|{{.Label "io.fucheng.vpc.deployment"}}'}else{'{{.Name}}|{{.Name}}|{{.Label "com.docker.compose.project"}}|{{.Label "io.fucheng.vpc.managed"}}|{{.Label "io.fucheng.vpc.deployment"}}'}
  $arguments=@($kind,'ls');if($kind -eq 'container'){$arguments+=@('-a','--no-trunc')};$raw=Invoke-VpcChecked ($arguments+@('--format',$format))
  foreach($line in @($raw -split "`r?`n"|Where-Object {$_})){$f=$line.Split('|');if($f[2] -cne 'fucheng' -and $f[1] -cnotmatch '^fucheng(?:$|_|-(?:app|backup|cloudflared)$|-op-)'){continue}
   $old=($AllowOld -and $f[3] -ceq 'tunnel-only-v1' -and (($kind -eq 'container' -and $f[1] -ceq 'fucheng-cloudflared' -and [IO.Path]::GetFullPath($f[5]) -ieq $composePath) -or ($kind -eq 'network' -and $f[1] -ceq 'fucheng_default')))
   $full=($DeploymentId -and $f[3] -ceq 'full-v1' -and $f[4] -ceq $DeploymentId)
   if($f[2] -cne 'fucheng' -or (!$old -and !$full)){throw 'UNKNOWN_FUCHENG_RESOURCE'}
   if($full -and $kind -eq 'container'){
    $service=if($f[1] -ceq 'fucheng-app'){'app'}elseif($f[1] -ceq 'fucheng-backup'){'backup'}elseif($f[1] -ceq 'fucheng-cloudflared'){'cloudflared'}else{''}
    if($service){if($f[6] -cne $service -or [IO.Path]::GetFullPath($f[5]) -ine $composePath){throw 'UNKNOWN_FUCHENG_RESOURCE'}}else{$names=@($journal.operations|ForEach-Object {$_.container});if($f[1] -cnotin $names -or $f[1] -cnotmatch ('^fucheng-op-'+$DeploymentId.Substring(0,12)+'-(backup|import|restore|verify)$')){throw 'UNKNOWN_FUCHENG_RESOURCE'}}
    $actual=Invoke-VpcChecked @('inspect','--type','container','--format','{{.Image}}',$f[0]);$expectedImage=if($service -ceq 'cloudflared'){$tunnelImageId}else{$appImageId};if($actual -cne $expectedImage){throw 'UNKNOWN_FUCHENG_RESOURCE'}
   }
   if($full -and $kind -eq 'network' -and $f[1] -cnotin @('fucheng_default','fucheng_origin')){throw 'UNKNOWN_FUCHENG_RESOURCE'}
   if($full -and $kind -eq 'volume' -and $f[1] -cne 'fucheng_data'){throw 'UNKNOWN_FUCHENG_RESOURCE'}
   if($kind -eq 'container'){$found.containers+=,[pscustomobject]@{id=$f[0];name=$f[1];old=$old}}elseif($kind -eq 'network'){$found.networks+=,[pscustomobject]@{id=$f[0];name=$f[1];old=$old}}else{$found.volumes+=,$f[0]}
  }
 }
 foreach($network in $found.networks){$members=(Invoke-VpcChecked @('network','inspect','--format','{{json .Containers}}',$network.id))|ConvertFrom-Json;foreach($property in @($members.PSObject.Properties)){if($property.Name -cnotin @($found.containers|ForEach-Object {$_.id})){throw 'UNKNOWN_FUCHENG_RESOURCE'}}}
 return $found
}

function Save-DeployJournal {
 $next=$journalPath+'.next';if(Test-Path -LiteralPath $next){throw 'JOURNAL_UPDATE_PENDING'};$text=$journal|ConvertTo-Json -Depth 12
 $stream=[IO.File]::Open($next,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);try{$bytes=$utf8.GetBytes($text);$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
 if(Test-Path -LiteralPath $journalPath){[IO.File]::Replace($next,$journalPath,[System.Management.Automation.Language.NullString]::Value)}else{[IO.File]::Move($next,$journalPath)}
}

function Test-DeployPublic {
 Add-Type -AssemblyName System.Net.Http;$handler=New-Object Net.Http.HttpClientHandler;$handler.AllowAutoRedirect=$false;$handler.UseCookies=$false;$client=New-Object Net.Http.HttpClient($handler);$client.Timeout=[TimeSpan]::FromSeconds(12);$client.MaxResponseContentBufferSize=4096;$response=$null;$old=[Net.ServicePointManager]::SecurityProtocol
 try{[Net.ServicePointManager]::SecurityProtocol=$old -bor [Net.SecurityProtocolType]::Tls12;$response=$client.GetAsync(($origin+'/api/health')).GetAwaiter().GetResult();if([int]$response.StatusCode -ne 200 -or $response.RequestMessage.RequestUri.AbsoluteUri -cne ($origin+'/api/health')){return $false};$bytes=$response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult();if($bytes.Length -gt 4096){return $false};$v=[Text.Encoding]::UTF8.GetString($bytes)|ConvertFrom-Json;return (@($v.PSObject.Properties).Count -eq 1 -and $v.status -ceq 'ok')}
 catch{return $false}finally{[Net.ServicePointManager]::SecurityProtocol=$old;if($response){$response.Dispose()};$client.Dispose()}
}

function Assert-DeployHealthy([bool]$IncludeConnector=$false) {
 foreach($name in @('fucheng-app','fucheng-backup')){if((Invoke-VpcChecked @('inspect','--type','container','--format','{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}',$name)) -cne 'running|healthy'){throw 'STACK_UNHEALTHY'}}
 if($IncludeConnector -and (Invoke-VpcChecked @('inspect','--type','container','--format','{{.State.Status}}','fucheng-cloudflared')) -cne 'running'){throw 'STACK_UNHEALTHY'}
}

$docker=$null;$lock=$null;$journal=$null;$sourceStopped=$false;$startedStack=$false;$done=$false;$stage='preflight';$owned=$null
try {
 Assert-VpcWindows;if($env:DOCKER_HOST){throw 'DOCKER_HOST_OVERRIDE'}
 $root=Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)) 'Fucheng'
 Assert-VpcNoLink $root;Assert-VpcOwner $root
 $composePath=Join-Path $root 'compose.yml';$journalPath=Join-Path $root 'deploy-journal.json';$markerPath=Join-Path $root 'owner.txt'
 foreach($p in @($composePath,$journalPath,$markerPath,(Join-Path $root 'setup.lock'))){Assert-VpcNoLink $p;Assert-VpcOwner $p}
 $lock=[IO.File]::Open((Join-Path $root 'setup.lock'),[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
 if(Test-Path -LiteralPath ($journalPath+'.next')){throw 'JOURNAL_UPDATE_PENDING'}
 $journal=[IO.File]::ReadAllText($journalPath)|ConvertFrom-Json
 if($journal.version -ne 1 -or $journal.id -cnotmatch '^[0-9a-f]{32}$' -or $journal.source_id -cnotmatch '^[0-9a-f]{64}$' -or $journal.target_volume -cne 'fucheng_data' -or $journal.old_default -isnot [bool]){throw 'JOURNAL_INVALID'}
 if($journal.phase -cnotin @('FAILED','COMPLETE') -or ($journal.phase -ceq 'FAILED' -and $journal.failure_code -cnotin @('PUBLIC_HEALTH_UNCONFIRMED','RECONNECT_FAILED'))){throw 'UNEXPECTED_DEPLOYMENT_PHASE'}
 $text=[IO.File]::ReadAllText($composePath)
 if([IO.File]::ReadAllText($markerPath) -cne ('fucheng-vpc-full-v1|'+(Get-VpcHash $text)) -or $text -cne (Get-DeployCompose $journal.id $journal.old_default)){throw 'UNKNOWN_MANAGED_FILES'}
 foreach($f in @('business_match','admin_match','media_match')){if($journal.verification.$f -isnot [bool] -or !$journal.verification.$f){throw 'PRESERVATION_NOT_CONFIRMED'}}
 $tool=Get-Command docker.exe -CommandType Application -ErrorAction Stop|Select-Object -First 1;$docker=$tool.Source
 if((Invoke-VpcChecked @('context','inspect','--format','{{.Endpoints.docker.Host}}')) -cnotmatch '^npipe:/+\./pipe/(?:docker_engine|dockerDesktopLinuxEngine)$'){throw 'LOCAL_DOCKER_REQUIRED'}
 $appImageId=Invoke-VpcChecked @('image','inspect','--format','{{.Id}}',$appImage);$tunnelImageId=Invoke-VpcChecked @('image','inspect','--format','{{.Id}}',$tunnelImage)
 if($journal.image_id -cne $appImageId){throw 'JOURNAL_IMAGE_MISMATCH'}
 $owned=Get-DeployResources $journal.id $journal.old_default
 if($journal.phase -ceq 'COMPLETE'){Assert-DeployHealthy $true;if(!(Test-DeployPublic)){throw 'PUBLIC_HEALTH_UNCONFIRMED'};Write-Host '既有正式部署健康通過；未重新啟動或還原。';return}
 foreach($name in @('fucheng-app','fucheng-backup','fucheng-cloudflared')){
  $items=@($owned.containers|Where-Object {$_.name -ceq $name -and !$_.old});if($items.Count -ne 1){throw 'UNKNOWN_FUCHENG_RESOURCE'}
  if((Invoke-VpcChecked @('inspect','--format','{{.State.Status}}',$items[0].id)) -cne 'exited'){throw 'STACK_NOT_STOPPED'}
 }
 $verifyOps=@($journal.operations|Where-Object {$_.name -ceq 'verify'})
 if($verifyOps.Count -ne 1 -or $verifyOps[0].status -cne 'complete' -or $verifyOps[0].exit_code -ne 0 -or $verifyOps[0].id -cnotmatch '^[a-f0-9]{64}$'){throw 'VERIFY_RECEIPT_INVALID'}
 $verifyId=$verifyOps[0].id
 $v=(Invoke-VpcChecked @('inspect','--format','{"image":{{json .Image}},"cmd":{{json .Config.Cmd}},"entry":{{json .Config.Entrypoint}},"mounts":{{json .Mounts}},"network":{{json .HostConfig.NetworkMode}},"readonly":{{json .HostConfig.ReadonlyRootfs}}}',$verifyId))|ConvertFrom-Json
 if($v.image -cne $appImageId -or ($v.entry -join '|') -cne 'python' -or @($v.cmd).Count -ne 2 -or $v.cmd[0] -cne '-c' -or $v.cmd[1] -cne (Get-DeployVerifierSource) -or $v.network -cne 'none' -or !$v.readonly -or @($v.mounts).Count -ne 2){throw 'VERIFY_CONTAINER_MISMATCH'}
 foreach($pair in @(@('/source','fucheng-check-v120_data'),@('/target','fucheng_data'))){$m=@($v.mounts|Where-Object {$_.Destination -ceq $pair[0]});if($m.Count -ne 1 -or $m[0].Type -cne 'volume' -or $m[0].Name -cne $pair[1] -or $m[0].RW){throw 'VERIFY_CONTAINER_MISMATCH'}}
 $source=Get-DeploySource;if($source.id -cne $journal.source_id){throw 'SOURCE_IDENTITY_MISMATCH'};Assert-DeployNoWriter $source.id
 $other=Invoke-VpcChecked @('container','ls','--quiet','--filter','volume=fucheng_data');if($other){throw 'OTHER_TARGET_WRITER'}
 $stage='stop_preview';if($source.state -ceq 'running'){$null=Invoke-VpcChecked @('stop','--time','45',$source.id) 55;$sourceStopped=$true}
 $again=Get-DeploySource;if($again.id -cne $source.id -or $again.state -cne 'exited'){throw 'SOURCE_STOP_UNCONFIRMED'};Assert-DeployNoWriter
 $stage='compare_current_data';$raw=Invoke-VpcChecked @('start','--attach',$verifyId) 90;$verified=$raw|ConvertFrom-Json
 foreach($field in @('ok','schema_match','integrity_ok','fk_ok','revision_match','business_match','admin_match','target_sessions_zero','media_match','source_preview_marked','target_preview_unmarked')){if($verified.$field -isnot [bool] -or !$verified.$field){throw 'DATA_CHANGED_REVIEW_REQUIRED'}}
 if($verified.source_admin_count -lt 1 -or $verified.source_admin_count -ne $verified.target_admin_count){throw 'DATA_CHANGED_REVIEW_REQUIRED'}
 Write-Host ('目前來源／新資料卷相同；管理員 '+[int]$verified.target_admin_count+' 位。未執行匯入或還原。')
 foreach($name in @('fucheng-app','fucheng-backup')){
  $startedStack=$true;$stage='start_'+$name;$resource=@($owned.containers|Where-Object {$_.name -ceq $name})[0]
  $null=Invoke-VpcChecked @('start',$resource.id) 20;$healthy=$false
  for($i=0;$i -lt 35;$i++){
   $state=Invoke-VpcChecked @('inspect','--format','{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}',$resource.id) 5
   if($state -ceq 'running|healthy'){$healthy=$true;break}
   if($state -notlike 'running|*'){break};Start-Sleep -Seconds 2
  };if(!$healthy){throw 'STACK_UNHEALTHY'};Write-Host ($name+' = healthy')
 }
 $stage='start_tunnel';$connector=@($owned.containers|Where-Object {$_.name -ceq 'fucheng-cloudflared'})[0];$null=Invoke-VpcChecked @('start',$connector.id) 20
 $stage='public_health';$passed=$false
 for($i=0;$i -lt 8;$i++){
  if(Test-DeployPublic){$passed=$true;break};Write-Host ('公開健康檢查尚未通過：'+($i+1)+'/8');if($i -lt 7){Start-Sleep -Seconds 3}
 }
 if(!$passed){throw 'PUBLIC_HEALTH_UNCONFIRMED'};Assert-DeployHealthy $true
 $journal.phase='COMPLETE';$journal.failure_code=$null;Save-DeployJournal;$done=$true
 Write-Host 'COMPLETE：固定網址、網站及備份健康通過。'
 Write-Host 'https://fucheng.momonong.workers.dev/；請用球館原帳密登入。'
}catch{
 $safe=@('PRIVATE_ACL_UNCONFIRMED','WINDOWS_CONSOLE_REQUIRED','LINKED_PATH','UNKNOWN_OWNER','SOURCE_VOLUME_MISMATCH','SOURCE_PREVIEW_MISMATCH','SOURCE_PORT_MISMATCH','DOCKER_HOST_OVERRIDE','JOURNAL_UPDATE_PENDING','JOURNAL_INVALID','UNEXPECTED_DEPLOYMENT_PHASE','UNKNOWN_MANAGED_FILES','PRESERVATION_NOT_CONFIRMED','LOCAL_DOCKER_REQUIRED','JOURNAL_IMAGE_MISMATCH','UNKNOWN_FUCHENG_RESOURCE','STACK_NOT_STOPPED','VERIFY_RECEIPT_INVALID','VERIFY_CONTAINER_MISMATCH','SOURCE_IDENTITY_MISMATCH','OTHER_SOURCE_WRITER','OTHER_TARGET_WRITER','SOURCE_STOP_UNCONFIRMED','DATA_CHANGED_REVIEW_REQUIRED','STACK_UNHEALTHY','PUBLIC_HEALTH_UNCONFIRMED','DOCKER_COMMAND_UNCONFIRMED')
 $code=if($_.Exception.Message -cin $safe){$_.Exception.Message}else{'UNCLASSIFIED'}
 if(($sourceStopped -or $startedStack) -and !$done){
  $safeToRecover=$true
  if($owned){foreach($r in $owned.containers){if($r.name -cin @('fucheng-cloudflared','fucheng-app','fucheng-backup')){
   try{$null=Invoke-VpcChecked @('stop','--time','45',$r.id) 55;if((Invoke-VpcChecked @('inspect','--format','{{.State.Status}}',$r.id)) -cne 'exited'){$safeToRecover=$false}}catch{$safeToRecover=$false;Write-Host ('安全停止未確認：'+$r.name)}
  }}}
  if($sourceStopped -and $safeToRecover){try{$again=Get-DeploySource;if($again.id -ceq $journal.source_id -and $again.state -ceq 'exited'){$null=Invoke-VpcChecked @('start',$again.id) 20};Write-Host '已嘗試重新啟動原 preview，網頁健康仍需另核對。'}catch{Write-Host '原 preview 重新啟動未確認；資料卷保留。'}}
  elseif(!$safeToRecover){Write-Host '新 stack 停止未確認，為避免雙站分別寫入，未啟動原 preview；請回傳停止代碼。'}
 }
 Write-Host ('停止：stage='+$stage+'；code='+$code+'；type='+$_.Exception.GetType().FullName)
 Write-Host '未執行 init／migration／匯入／還原；原卷與新卷均保留。'
}finally{if($lock){$lock.Dispose()}}
}
