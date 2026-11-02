& {
# Windows PowerShell 5.1. Fixed images, new-volume restore, private local input only.
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
function Set-VpcPrivatePath([string]$Path,[bool]$Directory) {
 $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User;$acl=if($Directory){New-Object Security.AccessControl.DirectorySecurity}else{New-Object Security.AccessControl.FileSecurity}
 $acl.SetOwner($sid);$acl.SetAccessRuleProtection($true,$false)
 foreach($principal in @($sid,(New-Object Security.Principal.SecurityIdentifier('S-1-5-18')),(New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))){
  $rule=if($Directory){New-Object Security.AccessControl.FileSystemAccessRule($principal,'FullControl','ContainerInherit,ObjectInherit','None','Allow')}else{New-Object Security.AccessControl.FileSystemAccessRule($principal,'FullControl','Allow')};[void]$acl.AddAccessRule($rule)
 };Set-Acl -LiteralPath $Path -AclObject $acl
}
function Get-VpcHash([string]$Text) {$sha=[Security.Cryptography.SHA256]::Create();try{return ([BitConverter]::ToString($sha.ComputeHash($utf8.GetBytes($Text)))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}}
function Assert-VpcToken([string]$Token) {
 if($Token.Length -gt 16384 -or $Token -cnotmatch '^[A-Za-z0-9+/]+={0,2}$'){throw 'INVALID_TOKEN'}
 try{$v=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Token))|ConvertFrom-Json;if($v.t -cne $tunnelId -or $v.a -isnot [string] -or !$v.a -or $v.s -isnot [string] -or !$v.s){throw 'INVALID_TOKEN'}}catch{throw 'INVALID_TOKEN'}
}
function Convert-VpcTokenInput([string]$InputText) {
 if($InputText.Length -gt 20000){throw 'INVALID_TOKEN_INPUT'};$text=$InputText.Trim()
 if($text -cmatch '^[A-Za-z0-9+/]+={0,2}$'){return $text}
 if($text -cnotmatch '^docker(?:\.exe)?[ \t]+run[ \t]+cloudflare/cloudflared:latest[ \t]+tunnel[ \t]+--no-autoupdate[ \t]+run[ \t]+--token[ \t]+([A-Za-z0-9+/]+={0,2})$'){throw 'INVALID_TOKEN_INPUT'}
 return $Matches[1]
}
function Invoke-VpcChecked([string[]]$Arguments,[int]$Limit=15) {$r=Invoke-ProbeDocker $Arguments $Limit;if($r.timed_out -or $r.exit_code -ne 0){throw 'DOCKER_COMMAND_UNCONFIRMED'};return $r.stdout}
function Get-DeployVerifierSource {
 return @'
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
}

function Get-DeployOldCompose {
 return @'
name: fucheng
services:
  cloudflared:
    image: cloudflare/cloudflared@sha256:faa8e0a1475f137c910be6025f43c8e4092fdd35461b31e19fd1390657a1ff39
    platform: linux/amd64
    container_name: fucheng-cloudflared
    command: [tunnel, --no-autoupdate, --protocol, quic, run, --token-file, /run/secrets/tunnel_token]
    secrets: [tunnel_token]
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    pids_limit: 64
    mem_limit: 256m
    cpus: 0.5
    restart: unless-stopped
    labels:
      io.fucheng.vpc.managed: tunnel-only-v1
    logging:
      driver: json-file
      options: {max-size: 1m, max-file: "2"}
networks:
  default:
    labels:
      io.fucheng.vpc.managed: tunnel-only-v1
secrets:
  tunnel_token:
    file: ./tunnel.token
'@
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
 return $text.Replace('DEFAULT_NETWORK',$network).Replace('APP_IMAGE',$appImage).Replace('TUNNEL_IMAGE',$tunnelImage).Replace('DEPLOY_ID',$Id)
}
function Test-DeployOverlap([string]$Left,[string]$Right) {
 $ranges=@();foreach($cidr in @($Left,$Right)){$parts=$cidr.Split('/');if($parts.Count -ne 2 -or [int]$parts[1] -lt 0 -or [int]$parts[1] -gt 32){throw 'ROUTE_FORMAT'};$ip=[Net.IPAddress]::Parse($parts[0]);if($ip.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork){throw 'ROUTE_FORMAT'};$b=$ip.GetAddressBytes();$n=[uint64]$b[0]*16777216+[uint64]$b[1]*65536+[uint64]$b[2]*256+$b[3];$size=[uint64][Math]::Pow(2,32-[int]$parts[1]);$start=[uint64]([Math]::Floor($n/$size)*$size);$ranges+=,@($start,($start+$size-1))};return ($ranges[0][0] -le $ranges[1][1] -and $ranges[1][0] -le $ranges[0][1])
}
function Assert-DeploySubnet {
 $ids=Invoke-VpcChecked @('network','ls','--quiet','--no-trunc');foreach($id in @($ids -split "`r?`n"|Where-Object {$_})){$json=Invoke-VpcChecked @('network','inspect','--format','{{json .IPAM.Config}}',$id);foreach($config in @($json|ConvertFrom-Json)){if($config.Subnet -and $config.Subnet -notmatch ':'){if(Test-DeployOverlap '172.30.98.0/24' $config.Subnet){throw 'SUBNET_CONFLICT'}}}}
 $routes=@(Get-NetRoute -AddressFamily IPv4 -ErrorAction Stop);if(!$routes.Count){throw 'ROUTE_UNCONFIRMED'};foreach($route in $routes){if($route.DestinationPrefix -ne '0.0.0.0/0' -and (Test-DeployOverlap '172.30.98.0/24' $route.DestinationPrefix)){throw 'SUBNET_CONFLICT'}}
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
function Set-DeployPhase([string]$Phase) {$journal.phase=$Phase;Save-DeployJournal;Write-Host ('階段：'+$Phase)}
function Read-DeployPrivate([string]$Prompt) {
 $secret=Read-Host $Prompt -AsSecureString;$bstr=[IntPtr]::Zero;try{$bstr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret);return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)}finally{if($bstr -ne [IntPtr]::Zero){[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)};$secret.Dispose()}
}
function Write-DeployPrivate([string]$Path,[string]$Value) {
 Assert-VpcNoLink $Path;$stream=[IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);$bytes=$null
 try{Set-VpcPrivatePath $Path $false;$bytes=$utf8.GetBytes($Value);$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{if($bytes){[Array]::Clear($bytes,0,$bytes.Length)};$stream.Dispose()}
}
function Invoke-DeployJob([string]$Name,[string[]]$Mounts,[string[]]$Environment,[string[]]$Command,[string]$EntryPoint='') {
 $op=[pscustomobject]@{name=$Name;container=('fucheng-op-'+$journal.id.Substring(0,12)+'-'+$Name);id=$null;status='pending';exit_code=$null};$journal.operations+=,$op;Save-DeployJournal
 $arguments=@('run','--detach','--name',$op.container,'--platform','linux/amd64','--pull','never','--network','none','--restart','no','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:size=32m,mode=1777','--label','com.docker.compose.project=fucheng','--label','io.fucheng.vpc.managed=full-v1','--label',('io.fucheng.vpc.deployment='+$journal.id),'--label',('io.fucheng.vpc.operation='+$Name))
 foreach($mount in $Mounts){$arguments+=@('--volume',$mount)};foreach($entry in $Environment){$arguments+=@('--env',$entry)};if($EntryPoint){$arguments+=@('--entrypoint',$EntryPoint)}
 $id=Invoke-VpcChecked ($arguments+@($appImage)+$Command) 30;if($id -cnotmatch '^[a-f0-9]{64}$'){throw 'OPERATION_UNKNOWN'};$op.id=$id;$op.status='running';Save-DeployJournal
 for($i=0;$i -lt 36;$i++){$v=Invoke-VpcChecked @('inspect','--type','container','--format','{{.State.Status}}|{{.State.ExitCode}}',$id) 5;if($v -cmatch '^exited\|([0-9]+)$'){$op.status='complete';$op.exit_code=[int]$Matches[1];Save-DeployJournal;if($op.exit_code -ne 0){throw 'OPERATION_FAILED'};return $id};if($v -cmatch '^(dead|removing)\|'){throw 'OPERATION_UNKNOWN'};Start-Sleep -Seconds 2};throw 'OPERATION_UNKNOWN'
}
function Get-DeployBackup {
 $files=@(Get-ChildItem -LiteralPath $checkpointDir -Filter '*.json');if($files.Count -ne 1){throw 'BACKUP_GROUP_UNCONFIRMED'};$info=[IO.File]::ReadAllText($files[0].FullName)|ConvertFrom-Json
 if($info.file -cnotmatch '^manual-[0-9TZ]+-[0-9a-f]{8}\.db$' -or $info.media_file -cne ($info.file -replace '\.db$','.media.tar') -or $info.revision -cne '0015_deployment_diagnostics' -or $info.restore_config.image_ref -cne $appImage){throw 'BACKUP_METADATA_MISMATCH'}
 foreach($pair in @(@($info.file,$info.sha256),@($info.media_file,$info.media_sha256))){$path=Join-Path $checkpointDir $pair[0];Assert-VpcNoLink $path;if(!(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $pair[1]){throw 'BACKUP_HASH_MISMATCH'}};return $info.file
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
function Stop-DeployExposure {
 $owned=Get-DeployResources $journal.id $journal.old_default
 foreach($resource in $owned.containers){if($resource.name -cin @('fucheng-cloudflared','fucheng-app','fucheng-backup')){$null=Invoke-VpcChecked @('stop','--time','45',$resource.id) 55;if((Invoke-VpcChecked @('inspect','--type','container','--format','{{.State.Status}}',$resource.id) 5) -cne 'exited'){throw 'STACK_STOP_UNCONFIRMED'}}}
}

$docker=$null;$lock=$null;$journal=$null;$journalPath=$null;$inThisRun=$false;$sourceStopped=$false;$root=$null;$stage='preflight'
try {
 Assert-VpcWindows;if($env:DOCKER_HOST){throw 'DOCKER_HOST_OVERRIDE'}
 $local=[Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData);if(!$local -or ![IO.Path]::IsPathRooted($local) -or $local -match '^\\\\' -or $local -match '(?i)(^|[\\/])OneDrive(?:[ -][^\\/]*)?([\\/]|$)'){throw 'LOCAL_DIRECTORY'}
 $root=Join-Path $local 'Fucheng';$composePath=Join-Path $root 'compose.yml';$markerPath=Join-Path $root 'owner.txt';$journalPath=Join-Path $root 'deploy-journal.json';Assert-VpcNoLink $root;$oldManaged=$false;$rootExisted=Test-Path -LiteralPath $root
 if(Test-Path -LiteralPath $root){
  Assert-VpcOwner $root;foreach($item in @(Get-ChildItem -LiteralPath $root -Force)){Assert-VpcNoLink $item.FullName;if($item.PSIsContainer){if($item.Name -cne 'backup'){throw 'UNKNOWN_DIRECTORY_CONTENT'};foreach($child in @(Get-ChildItem -LiteralPath $item.FullName -Recurse -Force)){Assert-VpcNoLink $child.FullName}}elseif($item.Name -cnotin @('owner.txt','compose.yml','setup.lock','tunnel.token','turnstile.secret','protected.env','deploy-journal.json','deploy-journal.json.next','connector-compose.before.yml','connector-owner.before.txt')){throw 'UNKNOWN_DIRECTORY_CONTENT'};Assert-VpcOwner $item.FullName}
  if(!(Test-Path -LiteralPath $markerPath -PathType Leaf) -or !(Test-Path -LiteralPath $composePath -PathType Leaf)){throw 'UNKNOWN_MANAGED_FILES'}
  $text=[IO.File]::ReadAllText($composePath);$marker=[IO.File]::ReadAllText($markerPath)
  if(Test-Path -LiteralPath ($journalPath+'.next')){throw 'JOURNAL_UPDATE_PENDING'}
  if(Test-Path -LiteralPath $journalPath){$journal=[IO.File]::ReadAllText($journalPath)|ConvertFrom-Json;if($journal.version -ne 1 -or $journal.id -cnotmatch '^[0-9a-f]{32}$' -or $journal.source_id -cnotmatch '^[0-9a-f]{64}$' -or $journal.target_volume -cne 'fucheng_data'){throw 'JOURNAL_INVALID'};if($marker -cne ('fucheng-vpc-full-v1|'+(Get-VpcHash $text)) -or $text -cne (Get-DeployCompose $journal.id $journal.old_default)){throw 'UNKNOWN_MANAGED_FILES'}}
  else{if($marker -cne ('fucheng-vpc-tunnel-only-v1|'+(Get-VpcHash $text)) -or $text.Replace("`r`n","`n") -cne (Get-DeployOldCompose).Replace("`r`n","`n")){throw 'UNKNOWN_MANAGED_FILES'};$oldManaged=$true}
 }
 $tool=Get-Command 'docker.exe' -CommandType Application -ErrorAction SilentlyContinue|Select-Object -First 1;if(!$tool){throw 'DOCKER_MISSING'};$docker=$tool.Source
 if((Invoke-VpcChecked @('context','inspect','--format','{{.Endpoints.docker.Host}}')) -cnotmatch '^npipe:/+\./pipe/(?:docker_engine|dockerDesktopLinuxEngine)$'){throw 'LOCAL_DOCKER_REQUIRED'}
 if((Invoke-VpcChecked @('info','--format','{{.OSType}}|{{.Architecture}}')) -cnotin @('linux|x86_64','linux|amd64')){throw 'LINUX_AMD64_REQUIRED'};$null=Invoke-VpcChecked @('compose','version','--short')
 $stage='images';$imageIds=@();foreach($ref in @($appImage,$tunnelImage)){$r=Invoke-ProbeDocker @('image','inspect','--format','{{.Id}}|{{.Os}}|{{.Architecture}}',$ref) 10;if($r.timed_out){throw 'IMAGE_UNKNOWN'};if($r.exit_code -ne 0){Write-Host '下載固定版本 image…';$null=Invoke-VpcChecked @('pull','--platform','linux/amd64',$ref) 180};$value=Invoke-VpcChecked @('image','inspect','--format','{{.Id}}|{{.Os}}|{{.Architecture}}',$ref);if($value -cnotmatch '^(sha256:[a-f0-9]{64})\|linux\|amd64$'){throw 'IMAGE_UNCONFIRMED'};$imageIds+=,$Matches[1]};$appImageId=$imageIds[0];$tunnelImageId=$imageIds[1]
 if($journal){
  if($journal.image_id -cne $appImageId){throw 'JOURNAL_IMAGE_MISMATCH'};$null=Get-DeployResources $journal.id $journal.old_default
  if($journal.phase -cne 'COMPLETE'){throw 'PARTIAL_DEPLOYMENT_REVIEW_REQUIRED'}
  $stage='existing_health';Assert-DeployHealthy $true;if(!(Test-DeployPublic)){throw 'PUBLIC_HEALTH_UNCONFIRMED'};Write-Host '既有正式部署健康核對通過；未重新備份／匯入／還原。';return
 }
 $stage='source';$source=Get-DeploySource;Assert-DeployNoWriter $source.id
 $stage='ownership';$resources=Get-DeployResources '' $oldManaged
 $stage='network';Assert-DeploySubnet
 $stage='private_input';$tokenPath=Join-Path $root 'tunnel.token';$pendingToken=$null
 if(Test-Path -LiteralPath $tokenPath -PathType Leaf){$private=[IO.File]::ReadAllText($tokenPath);Assert-VpcToken $private;$private=$null}else{$pendingToken=Convert-VpcTokenInput (Read-DeployPrivate '貼上 fucheng Tunnel token 或 Cloudflare 完整 Docker 命令（隱藏，不要貼到聊天）');Assert-VpcToken $pendingToken}
 if((Test-Path -LiteralPath (Join-Path $root 'turnstile.secret')) -or (Test-Path -LiteralPath (Join-Path $root 'protected.env'))){throw 'UNJOURNALED_KEYS'}
 $pendingSitekey=Read-DeployPrivate '貼上新 lowercase fucheng Turnstile sitekey（隱藏）';if($pendingSitekey -cnotmatch '^[A-Za-z0-9_-]{20,128}$'){throw 'INVALID_SITEKEY'}
 $pendingSecret=Read-DeployPrivate '貼上新 lowercase fucheng Turnstile secret（隱藏）';if($pendingSecret -cnotmatch '^[A-Za-z0-9_-]{20,128}$'){throw 'INVALID_TURNSTILE_SECRET'}
 $stage='preparation';if(!$rootExisted){$null=New-Item -ItemType Directory -Path $root -ErrorAction Stop};Set-VpcPrivatePath $root $true
 $lock=[IO.File]::Open((Join-Path $root 'setup.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
 if((Test-Path -LiteralPath $journalPath) -or (Test-Path -LiteralPath ($journalPath+'.next'))){throw 'CONCURRENT_SETUP_DETECTED'}
 Assert-VpcNoLink $root;if($oldManaged){if([IO.File]::ReadAllText($composePath) -cne $text -or [IO.File]::ReadAllText($markerPath) -cne $marker){throw 'CONCURRENT_SETUP_DETECTED'}}elseif(@(Get-ChildItem -LiteralPath $root -Force|Where-Object {$_.Name -cne 'setup.lock'}).Count){throw 'CONCURRENT_SETUP_DETECTED'}
 if((Test-Path -LiteralPath (Join-Path $root 'turnstile.secret')) -or (Test-Path -LiteralPath (Join-Path $root 'protected.env'))){throw 'CONCURRENT_SETUP_DETECTED'}
 $again=Get-DeploySource;if($again.id -cne $source.id){throw 'CONCURRENT_SETUP_DETECTED'};Assert-DeployNoWriter $source.id;$resources=Get-DeployResources '' $oldManaged
 if($oldManaged){foreach($pair in @(@($composePath,'connector-compose.before.yml'),@($markerPath,'connector-owner.before.txt'))){$destination=Join-Path $root $pair[1];if(Test-Path -LiteralPath $destination){throw 'EXISTING_CONNECTOR_BACKUP'};[IO.File]::Copy($pair[0],$destination,$false)}}
 $journal=[pscustomobject]@{version=1;id=[Guid]::NewGuid().ToString('N');source_id=$source.id;source_was_running=($source.state -ceq 'running');image_id=$appImageId;target_volume='fucheng_data';old_default=(@($resources.networks|Where-Object {$_.name -ceq 'fucheng_default'}).Count -eq 1);phase='PREPARING';operations=@();backup_file=$null;verification=$null;failure_code=$null;preview_recovered=$false};Save-DeployJournal;$inThisRun=$true
 $compose=Get-DeployCompose $journal.id $journal.old_default;[IO.File]::WriteAllText($composePath,$compose,$utf8);[IO.File]::WriteAllText($markerPath,('fucheng-vpc-full-v1|'+(Get-VpcHash $compose)),$utf8)
 if($null -ne $pendingToken){Write-DeployPrivate $tokenPath $pendingToken}else{Set-VpcPrivatePath $tokenPath $false};$pendingToken=$null
 Write-DeployPrivate (Join-Path $root 'protected.env') ('FUCHENG_TURNSTILE_SITEKEY='+$pendingSitekey);$pendingSitekey=$null
 Write-DeployPrivate (Join-Path $root 'turnstile.secret') $pendingSecret;$pendingSecret=$null;Set-DeployPhase 'PREPARED'
 $composeArgs=@('compose','--project-directory',$root,'--project-name','fucheng','--env-file',(Join-Path $root 'protected.env'),'--file',$composePath)
 $checkpointDir=Join-Path $root ('backup/checkpoint-'+$journal.id);$liveBackup=Join-Path $root 'backup/live';foreach($directory in @($checkpointDir,$liveBackup)){Assert-VpcNoLink $directory;if(Test-Path -LiteralPath $directory){throw 'EXISTING_BACKUP_TARGET'};$null=New-Item -ItemType Directory -Path $directory -Force}
 $stage='stop_connector';Set-DeployPhase 'CONNECTOR_STOPPING';foreach($connector in $resources.containers){$null=Invoke-VpcChecked @('stop','--time','20',$connector.id) 30}
 $stage='stop_source';Set-DeployPhase 'SOURCE_STOPPING';$again=Get-DeploySource;if($again.id -cne $journal.source_id){throw 'SOURCE_IDENTITY_MISMATCH'};if($again.state -ceq 'running'){$null=Invoke-VpcChecked @('stop','--time','45',$journal.source_id) 55};$again=Get-DeploySource;if($again.id -cne $journal.source_id -or $again.state -cne 'exited'){throw 'SOURCE_STOP_UNCONFIRMED'};$sourceStopped=$true;Assert-DeployNoWriter;Set-DeployPhase 'SOURCE_STOPPED'
 $previewEnv=@('FUCHENG_LOCAL_HTTP_PREVIEW=true','FUCHENG_PUBLIC_ORIGIN=http://localhost:8052','FUCHENG_COOKIE_SECURE=false','FUCHENG_PROXY_KIND=local','FUCHENG_TRUSTED_PROXY=','FUCHENG_BASE_PATH=',('FUCHENG_IMAGE_REF='+$appImage))
 $opsEnv=@(('FUCHENG_IMAGE_REF='+$appImage),'FUCHENG_BASE_PATH=',('FUCHENG_RESTORE_PUBLIC_ORIGIN='+$origin),'FUCHENG_RESTORE_PROXY_KIND=cloudflare')
 $stage='backup';$null=Invoke-DeployJob 'backup' @('fucheng-check-v120_data:/data',($checkpointDir+':/backups')) $previewEnv @('backup');$journal.backup_file=Get-DeployBackup;Set-DeployPhase 'BACKUP_CONFIRMED'
 $stage='new_volume';$null=Get-DeployResources $journal.id $journal.old_default;Set-DeployPhase 'TARGET_CREATING';$null=Invoke-VpcChecked @('volume','create','--label','com.docker.compose.project=fucheng','--label','io.fucheng.vpc.managed=full-v1','--label',('io.fucheng.vpc.deployment='+$journal.id),'fucheng_data');$labels=(Invoke-VpcChecked @('volume','inspect','--format','{{json .Labels}}','fucheng_data'))|ConvertFrom-Json;if($labels.'com.docker.compose.project' -cne 'fucheng' -or $labels.'io.fucheng.vpc.managed' -cne 'full-v1' -or $labels.'io.fucheng.vpc.deployment' -cne $journal.id){throw 'UNKNOWN_FUCHENG_RESOURCE'};Set-DeployPhase 'TARGET_CREATED'
 $stage='import';$null=Invoke-DeployJob 'import' @('fucheng_data:/data',($liveBackup+':/backups'),($checkpointDir+':/incoming:ro')) $opsEnv @('import-backup',$journal.backup_file);Set-DeployPhase 'IMPORT_CONFIRMED'
 $stage='restore';$null=Invoke-DeployJob 'restore' @('fucheng_data:/data',($liveBackup+':/backups')) $opsEnv @('restore',$journal.backup_file);Set-DeployPhase 'RESTORE_CONFIRMED'
 $stage='preservation';Assert-DeployNoWriter;$verifyId=Invoke-DeployJob 'verify' @('fucheng-check-v120_data:/source:ro','fucheng_data:/target:ro') @() @('-c',(Get-DeployVerifierSource)) 'python'
 $raw=Invoke-VpcChecked @('logs','--tail','2',$verifyId);$verified=$raw|ConvertFrom-Json
 foreach($field in @('ok','schema_match','integrity_ok','fk_ok','revision_match','business_match','admin_match','target_sessions_zero','media_match','source_preview_marked','target_preview_unmarked')){if($verified.$field -isnot [bool] -or !$verified.$field){throw 'DATA_VERIFY_FAILED'}}
 if($verified.source_admin_count -lt 1 -or $verified.source_admin_count -ne $verified.target_admin_count){throw 'ADMIN_PRESERVATION_FAILED'};$journal.verification=@{business_match=$true;admin_match=$true;media_match=$true;admin_count=[int]$verified.target_admin_count;sessions_expired=$true};Set-DeployPhase 'DATA_VERIFIED';Write-Host ('帳號／業務／媒體相同；管理員筆數：'+[int]$verified.target_admin_count+'；舊登入session已失效，請重新登入。')
 $stage='app_backup';$null=Get-DeployResources $journal.id $journal.old_default;$null=Invoke-VpcChecked ($composeArgs+@('up','--detach','--no-build','--pull','never','--wait','--wait-timeout','120','app','backup')) 135;Assert-DeployHealthy;Set-DeployPhase 'APP_BACKUP_HEALTHY'
 $stage='connector';$null=Invoke-VpcChecked ($composeArgs+@('up','--detach','--no-build','--pull','never','cloudflared')) 45;Set-DeployPhase 'CONNECTOR_STARTED'
 $stage='public_health';$public=$false;for($i=0;$i -lt 6;$i++){if(Test-DeployPublic){$public=$true;break};if($i -lt 5){Start-Sleep -Seconds 3}};if(!$public){throw 'PUBLIC_HEALTH_UNCONFIRMED'};Assert-DeployHealthy $true;Set-DeployPhase 'COMPLETE'
 Write-Host '網站與專用 Tunnel 已完成本機及公開 health 核對：https://fucheng.momonong.workers.dev'
 Write-Host '原預覽資料卷、故障資料及本機成組備份保留；未變更 momonong.me。會員操作／Turnstile實際互動及Windows冷開機仍待人工驗收。'
} catch {
 $allowed=@('PRIVATE_ACL_UNCONFIRMED','DOCKER_HOST_OVERRIDE','LOCAL_DIRECTORY','WINDOWS_CONSOLE_REQUIRED','LINKED_PATH','UNKNOWN_OWNER','UNKNOWN_DIRECTORY_CONTENT','UNKNOWN_MANAGED_FILES','JOURNAL_UPDATE_PENDING','JOURNAL_INVALID','JOURNAL_IMAGE_MISMATCH','DOCKER_MISSING','LOCAL_DOCKER_REQUIRED','LINUX_AMD64_REQUIRED','DOCKER_COMMAND_UNCONFIRMED','IMAGE_UNKNOWN','IMAGE_UNCONFIRMED','PARTIAL_DEPLOYMENT_REVIEW_REQUIRED','SOURCE_IDENTITY_MISMATCH','SOURCE_VOLUME_MISMATCH','SOURCE_PREVIEW_MISMATCH','SOURCE_PORT_MISMATCH','OTHER_SOURCE_WRITER','UNKNOWN_FUCHENG_RESOURCE','SUBNET_CONFLICT','ROUTE_FORMAT','ROUTE_UNCONFIRMED','INVALID_TOKEN','INVALID_TOKEN_INPUT','UNJOURNALED_KEYS','INVALID_SITEKEY','INVALID_TURNSTILE_SECRET','EXISTING_CONNECTOR_BACKUP','EXISTING_BACKUP_TARGET','CONCURRENT_SETUP_DETECTED','SOURCE_STOP_UNCONFIRMED','OPERATION_UNKNOWN','OPERATION_FAILED','BACKUP_GROUP_UNCONFIRMED','BACKUP_METADATA_MISMATCH','BACKUP_HASH_MISMATCH','DATA_VERIFY_FAILED','ADMIN_PRESERVATION_FAILED','STACK_UNHEALTHY','PUBLIC_HEALTH_UNCONFIRMED')
 $code=if($_.Exception.Message -cin $allowed){$_.Exception.Message}else{'UNCLASSIFIED'};$type=$_.Exception.GetType().FullName
 if($inThisRun -and $journal){$safeToRecover=$false;try{Stop-DeployExposure;$safeToRecover=$true}catch{Write-Host '新 stack 停止未確認，為避免雙站分別寫入，未啟動原 preview；保留資料與原operation，請勿重跑還原。'};if($safeToRecover -and $journal.source_was_running){try{$again=Get-DeploySource;if($again.id -ceq $journal.source_id -and $again.image -ceq $appImageId){if($again.state -ceq 'exited'){$null=Invoke-VpcChecked @('start',$journal.source_id) 30};$again=Get-DeploySource;$journal.preview_recovered=($again.id -ceq $journal.source_id -and $again.state -ceq 'running')}}catch{}};$journal.phase='FAILED';$journal.failure_code=$code;try{Save-DeployJournal}catch{Write-Host 'journal保存未確認，原operation證據保留。'}}
 Write-Host ('停止：stage='+$stage+'；code='+$code+'；type='+$type+'。不回顯原始錯誤／金鑰。')
 if($inThisRun -and $journal){Write-Host ('原preview容器重新運行確認：'+[bool]$journal.preview_recovered+'；未另驗證preview網頁健康。新volume／備份保留，部分或未知操作不可盲目重送。')}
} finally {$private=$null;$pendingToken=$null;$pendingSitekey=$null;$pendingSecret=$null;if($lock){$lock.Dispose()}}

}
