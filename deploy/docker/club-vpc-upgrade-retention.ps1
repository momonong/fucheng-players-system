#requires -Version 5.1
param([string]$TargetImage,[string]$ExpectedImageId)
# Code-only upgrade from 1.3.0 or 1.4.0. Requires the completed managed receipt chain.
# Dot sourcing only loads functions for offline regression. Run with -File in Windows.
$ErrorActionPreference='Stop';$utf8=New-Object Text.UTF8Encoding($false)
$originalImage='momonong/fucheng-players-system@sha256:0e5a297b0d16876fa56e1b9bed0470c3b8632d55ded6b23ffc5c18315f39e6e2'
$originalImageId='sha256:2cfa6229bc207b1df68aac4ef94baadb8a5b8bf149f536f1e3f3ee45d0403034'
$oldImage='momonong/fucheng-players-system@sha256:9b8931bd9042d932cbb0ff4f3b30fba82390d9478bac38a9444780efbe919e1e'
$oldImageId='sha256:63da2c4ddd162c56d2e68e7a7b88a02978081e857b1b850620af109c43564925'
$v140Image='momonong/fucheng-players-system@sha256:ee43b382014048d2fc12ed6a6a58c27563eee1cc9ae6ffba1cd9c0451a85e48e'
$v140ImageId='sha256:3adc4ee8ee494b4e25b2ea12b929b8a15a6d1449a1f624356b8b0b44823a4ca0'
$appImage=$oldImage
$tunnelImage='cloudflare/cloudflared@sha256:faa8e0a1475f137c910be6025f43c8e4092fdd35461b31e19fd1390657a1ff39'
$origin='https://fucheng.momonong.workers.dev'
# The following Windows, ACL, process, recipe, and HTTP helpers are retained from
# club-vpc-reconnect.ps1 / club-vpc-deploy.ps1. No secret file content is read here.
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

function Invoke-VpcChecked([string[]]$Arguments,[int]$Limit=15) {
 $r=Invoke-ProbeDocker $Arguments $Limit
 if($r.timed_out -or $r.exit_code -ne 0){
  $command=$Arguments[0..1] -join ' '
  Write-Host ('DOCKER_FAILED: '+$command+'; exit='+$r.exit_code+'; timeout='+$r.timed_out)
  # Only known metadata reads can reveal bounded stderr. No command payload,
  # raw inspect output, application logs, or write-operation stderr is emitted.
  if($command -cmatch '^(context inspect|info --format|image inspect|inspect --type|inspect --format|container ls|volume inspect|network inspect)$'){
   Write-Host ('ERROR: '+$r.stderr.Substring(0,[Math]::Min(1500,$r.stderr.Length)))
  }
  throw 'DOCKER_COMMAND_UNCONFIRMED'
 }
 return $r.stdout
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

function Test-DeployPublic {
 Add-Type -AssemblyName System.Net.Http;$handler=New-Object Net.Http.HttpClientHandler;$handler.AllowAutoRedirect=$false;$handler.UseCookies=$false;$client=New-Object Net.Http.HttpClient($handler);$client.Timeout=[TimeSpan]::FromSeconds(12);$client.MaxResponseContentBufferSize=4096;$response=$null;$old=[Net.ServicePointManager]::SecurityProtocol
 try{[Net.ServicePointManager]::SecurityProtocol=$old -bor [Net.SecurityProtocolType]::Tls12;$response=$client.GetAsync(($origin+'/api/health')).GetAwaiter().GetResult();if([int]$response.StatusCode -ne 200 -or $response.RequestMessage.RequestUri.AbsoluteUri -cne ($origin+'/api/health')){return $false};$bytes=$response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult();if($bytes.Length -gt 4096){return $false};$v=[Text.Encoding]::UTF8.GetString($bytes)|ConvertFrom-Json;return (@($v.PSObject.Properties).Count -eq 1 -and $v.status -ceq 'ok')}
 catch{return $false}finally{[Net.ServicePointManager]::SecurityProtocol=$old;if($response){$response.Dispose()};$client.Dispose()}
}

function Assert-DeployHealthy([bool]$IncludeConnector=$false) {
 foreach($name in @('fucheng-app','fucheng-backup')){if((Invoke-VpcChecked @('inspect','--type','container','--format','{{.State.Status}}|{{with index .State "Health"}}{{.Status}}{{end}}',$name)) -cne 'running|healthy'){throw 'STACK_UNHEALTHY'}}
 if($IncludeConnector -and (Invoke-VpcChecked @('inspect','--type','container','--format','{{.State.Status}}','fucheng-cloudflared')) -cne 'running'){throw 'STACK_UNHEALTHY'}
}
function Set-VpcPrivatePath([string]$Path,[bool]$Directory) {
 $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User;$acl=if($Directory){New-Object Security.AccessControl.DirectorySecurity}else{New-Object Security.AccessControl.FileSecurity}
 $acl.SetOwner($sid);$acl.SetAccessRuleProtection($true,$false)
 foreach($principal in @($sid,(New-Object Security.Principal.SecurityIdentifier('S-1-5-18')),(New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))){
  $rule=if($Directory){New-Object Security.AccessControl.FileSystemAccessRule($principal,'FullControl','ContainerInherit,ObjectInherit','None','Allow')}else{New-Object Security.AccessControl.FileSystemAccessRule($principal,'FullControl','Allow')};[void]$acl.AddAccessRule($rule)
 };Set-Acl -LiteralPath $Path -AclObject $acl
}

function Get-UpgradeRoot {
 return Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)) 'Fucheng'
}

function Write-UpgradeFile([string]$Path,[string]$Text) {
 Assert-VpcNoLink $Path
 $stream=[IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
 try{$bytes=$utf8.GetBytes($Text);$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
 Assert-VpcOwner $Path
}

function Save-UpgradeJournal {
 $next=$upgradeJournalPath+'.next';if(Test-Path -LiteralPath $next){throw 'JOURNAL_UPDATE_PENDING'}
 Write-UpgradeFile $next ($journal|ConvertTo-Json -Depth 15)
 if(Test-Path -LiteralPath $upgradeJournalPath){[IO.File]::Replace($next,$upgradeJournalPath,[System.Management.Automation.Language.NullString]::Value)}else{[IO.File]::Move($next,$upgradeJournalPath)}
}

function Set-UpgradePhase([string]$Phase) {
 $journal.phase=$Phase;Save-UpgradeJournal;Write-Host ('階段：'+$Phase)
}

function Assert-UpgradeNoWriter([string[]]$Allowed=@()) {
 $ids=Invoke-VpcChecked @('container','ls','--quiet','--no-trunc','--filter','volume=fucheng_data')
 foreach($id in @($ids -split "`r?`n"|Where-Object {$_})){
  if($id -cin $Allowed){continue}
  $v=(Invoke-VpcChecked @('inspect','--type','container','--format','{"id":{{json .Id}},"mounts":{{json .Mounts}}}',$id))|ConvertFrom-Json
  foreach($m in @($v.mounts)){if($m.Type -ceq 'volume' -and $m.Name -ceq 'fucheng_data' -and $m.RW){throw 'OTHER_TARGET_WRITER'}}
 }
}

function Test-UpgradeImageIdentity([string]$Actual,[string]$Reference,[string]$ConfigId) {
 # Classic Docker reports config ID; containerd-backed Docker may report the
 # pinned manifest digest. Only these two exact, reviewed identities are valid.
 if($ConfigId -cnotmatch '^sha256:[a-f0-9]{64}$'){return $false}
 if($Reference -cnotmatch '^.+@(sha256:[a-f0-9]{64})$'){return $false}
 $manifestId=$Matches[1]
 return ($Actual -ceq $ConfigId -or $Actual -ceq $manifestId)
}

function Get-UpgradeContainer([string]$Name) {
 $format='{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Image}},"ref":{{json .Config.Image}},"state":{{json .State.Status}},"health":{{with index .State "Health"}}{{json .Status}}{{else}}null{{end}},"labels":{{json .Config.Labels}},"mounts":{{json .Mounts}},"networks":{{json .NetworkSettings.Networks}},"ports":{{json .HostConfig.PortBindings}},"command":{{json .Config.Cmd}},"user":{{json .Config.User}},"readonly":{{json .HostConfig.ReadonlyRootfs}},"network_mode":{{json .HostConfig.NetworkMode}}}'
 return (Invoke-VpcChecked @('inspect','--type','container','--format',$format,$Name))|ConvertFrom-Json
}

function Assert-UpgradeMember([string]$Service,[string]$Ref,[string]$ImageId,[bool]$RequireHealthy=$true,[bool]$AllowMixed=$false) {
 if($Service -cnotin @('app','backup','cloudflared')){throw 'STACK_IDENTITY_MISMATCH'}
  $name='fucheng-'+$service;$v=Get-UpgradeContainer $name
  $expectedRef=if($service -ceq 'cloudflared'){$tunnelImage}else{$Ref}
  $expectedId=if($service -ceq 'cloudflared'){$tunnelImageId}else{$ImageId}
  # Only failure cleanup accepts a partially recreated stack. Each writer still
  # has to match one of the two independently verified immutable image pins.
  if($AllowMixed -and $service -cne 'cloudflared' -and $v.ref -ceq $oldImage){$expectedRef=$oldImage;$expectedId=$oldImageId}
  if($v.id -cnotmatch '^[0-9a-f]{64}$' -or $v.name -cne ('/'+$name) -or !(Test-UpgradeImageIdentity $v.image $expectedRef $expectedId) -or $v.ref -cne $expectedRef -or !$v.readonly -or $v.state -cnotin @('running','exited','created','restarting','paused','dead')){throw 'STACK_IDENTITY_MISMATCH'}
  $labels=$v.labels
  if($labels.'com.docker.compose.project' -cne 'fucheng' -or $labels.'com.docker.compose.service' -cne $service -or $labels.'io.fucheng.vpc.managed' -cne 'full-v1' -or $labels.'io.fucheng.vpc.deployment' -cne $deployment.id -or !$labels.'com.docker.compose.project.config_files' -or [IO.Path]::GetFullPath($labels.'com.docker.compose.project.config_files') -ine $composePath){throw 'STACK_IDENTITY_MISMATCH'}
  if(@($v.ports.PSObject.Properties).Count -ne 0){throw 'STACK_IDENTITY_MISMATCH'}
  if($RequireHealthy -and ($v.state -cne 'running' -or ($service -cne 'cloudflared' -and $v.health -cne 'healthy'))){throw 'STACK_UNHEALTHY'}
  $cmd=if($service -ceq 'app'){'serve'}elseif($service -ceq 'backup'){'backup-loop'}else{'tunnel|--no-autoupdate|--protocol|quic|run|--token-file|/run/secrets/tunnel_token'}
  if(($v.command -join '|') -cne $cmd){throw 'STACK_IDENTITY_MISMATCH'}
  $expectedMountCount=if($service -ceq 'cloudflared'){1}else{2}
  if(@($v.mounts).Count -ne $expectedMountCount){throw 'STACK_IDENTITY_MISMATCH'}
  if($service -cne 'cloudflared'){
   if($v.user -cne '10001:10001'){throw 'STACK_IDENTITY_MISMATCH'}
   $data=@($v.mounts|Where-Object {$_.Destination -ceq '/data'})
   if($data.Count -ne 1 -or $data[0].Type -cne 'volume' -or $data[0].Name -cne 'fucheng_data' -or !$data[0].RW){throw 'STACK_IDENTITY_MISMATCH'}
  }
  $extra=if($service -ceq 'app'){@('/run/secrets/turnstile_secret',(Join-Path $root 'turnstile.secret'),$false)}elseif($service -ceq 'backup'){@('/backups',(Join-Path $root 'backup/live'),$true)}else{@('/run/secrets/tunnel_token',(Join-Path $root 'tunnel.token'),$false)}
  $mount=@($v.mounts|Where-Object {$_.Destination -ceq $extra[0]})
  # Docker Desktop normalizes host bind sources; compare the canonical Windows
  # source without reading a secret. Reject unexpected source/mount recipes.
  if($mount.Count -ne 1 -or $mount[0].Type -cne 'bind' -or [bool]$mount[0].RW -ne $extra[2]){throw 'STACK_IDENTITY_MISMATCH'}
  $source=$mount[0].Source.Replace('/','\');$expected=$extra[1].Replace('/','\')
  if($source -cmatch '^\\run\\desktop\\mnt\\host\\([a-z])\\'){$source=$Matches[1]+':\'+$source.Substring($Matches[0].Length)}
  if($source -ine $expected){throw 'STACK_IDENTITY_MISMATCH'}
  $nets=@($v.networks.PSObject.Properties.Name)
  if($service -ceq 'backup'){if($v.network_mode -cne 'none' -or $nets.Count -ne 1 -or $nets[0] -cne 'none'){throw 'STACK_IDENTITY_MISMATCH'}}else{
   if($nets.Count -ne 2 -or 'fucheng_origin' -cnotin $nets -or 'fucheng_default' -cnotin $nets){throw 'STACK_IDENTITY_MISMATCH'}
   $ip=if($service -ceq 'app'){'172.30.98.2'}else{'172.30.98.3'}
   if($v.state -ceq 'running' -and $v.networks.fucheng_origin.IPAddress -cne $ip){throw 'STACK_IDENTITY_MISMATCH'}
  }
  return [pscustomobject]@{service=$service;id=$v.id;name=$name;state=$v.state}
}

function Assert-UpgradeIdentity([string]$Ref,[string]$ImageId,[bool]$RequireHealthy=$true,[bool]$AllowMixed=$false) {
 $stack=@()
 foreach($service in @('app','backup','cloudflared')){$stack+=,(Assert-UpgradeMember $service $Ref $ImageId $RequireHealthy $AllowMixed)}
 # Match every project container against the exact current/historical receipt.
 $raw=Invoke-VpcChecked @('container','ls','-a','--no-trunc','--format','{{.ID}}|{{.Names}}|{{.Label "com.docker.compose.project"}}')
 $receiptOps=@($deployment.operations)+@($priorUpgrade.operations)+@($intermediateUpgrade.operations)+@($journal.operations)
 foreach($line in @($raw -split "`r?`n"|Where-Object {$_})){
  $parts=$line.Split('|');if($parts.Count -ne 3){throw 'STACK_IDENTITY_MISMATCH'}
  if($parts[2] -cne 'fucheng' -and $parts[1] -cnotmatch '^fucheng-(?:app|backup|cloudflared|op-|upgrade-)'){continue}
  if($parts[0] -cin @($stack|ForEach-Object {$_.id})){continue}
  $matching=@($receiptOps|Where-Object {$_.id -ceq $parts[0]})
  if($matching.Count -ne 1 -or $parts[1] -cne $matching[0].container -or $parts[2] -cne 'fucheng'){throw 'UNKNOWN_FUCHENG_RESOURCE'}
  $state=Invoke-VpcChecked @('inspect','--format','{{.State.Status}}',$parts[0]);if($state -cne 'exited'){throw 'UNKNOWN_FUCHENG_RESOURCE'}
 }
 $volume=(Invoke-VpcChecked @('volume','inspect','--format','{{json .Labels}}','fucheng_data'))|ConvertFrom-Json
 if($volume.'com.docker.compose.project' -cne 'fucheng' -or $volume.'io.fucheng.vpc.managed' -cne 'full-v1' -or $volume.'io.fucheng.vpc.deployment' -cne $deployment.id){throw 'STACK_IDENTITY_MISMATCH'}
 $net=(Invoke-VpcChecked @('network','inspect','--format','{"internal":{{json .Internal}},"ipam":{{json .IPAM.Config}},"containers":{{json .Containers}},"labels":{{json .Labels}}}','fucheng_origin'))|ConvertFrom-Json
 if(!$net.internal -or @($net.ipam).Count -ne 1 -or $net.ipam[0].Subnet -cne '172.30.98.0/24' -or $net.labels.'io.fucheng.vpc.managed' -cne 'full-v1' -or $net.labels.'io.fucheng.vpc.deployment' -cne $deployment.id){throw 'STACK_IDENTITY_MISMATCH'}
 foreach($property in @($net.containers.PSObject.Properties)){if($property.Name -cnotin @($stack|ForEach-Object {$_.id})){throw 'UNKNOWN_FUCHENG_RESOURCE'}}
 return ,$stack
}

function Assert-UpgradeCompletedReceipt($Receipt,$Directory,[string]$Source,[string]$SourceId,[string]$Target,[string]$TargetId) {
 # Both persisted image IDs are canonical config IDs, unlike Docker's .Image.
 if($Receipt.version -ne 1 -or $Receipt.id -cnotmatch '^[a-f0-9]{32}$' -or $Directory.Name -cne ('upgrade-'+$Receipt.id) -or $Receipt.deployment_id -cne $deployment.id -or $Receipt.old_image -cne $Source -or $Receipt.old_image_id -cne $SourceId -or $Receipt.target_image -cne $Target -or $Receipt.target_image_id -cne $TargetId -or $Receipt.phase -cne 'COMPLETE' -or $null -ne $Receipt.failure_code -or $null -ne $Receipt.stop_confirmed){throw 'JOURNAL_INVALID'}
 $ops=@($Receipt.operations)
 if($ops.Count -ne 3 -or @($ops.id|Select-Object -Unique).Count -ne 3){throw 'JOURNAL_INVALID'}
 for($i=0;$i -lt 3;$i++){
  $op=$ops[$i];$name=@('backup','before','after')[$i]
  if($op.name -cne $name -or $op.container -cne ('fucheng-upgrade-'+$Receipt.id+'-'+$name) -or $op.id -cnotmatch '^[a-f0-9]{64}$' -or $op.status -cne 'complete' -or $op.exit_code -isnot [ValueType] -or $op.exit_code -ne 0){throw 'JOURNAL_INVALID'}
 }
 foreach($summary in @($Receipt.before,$Receipt.after)){
  if(!$summary -or $summary.ok -isnot [bool] -or !$summary.ok -or $summary.schema -cne '0015_deployment_diagnostics' -or $summary.digest -cnotmatch '^[a-f0-9]{64}$' -or $summary.media_digest -cnotmatch '^[a-f0-9]{64}$' -or $summary.admin_count -isnot [ValueType] -or $summary.admin_count -lt 1 -or $summary.integrity_ok -isnot [bool] -or !$summary.integrity_ok -or $summary.fk_ok -isnot [bool] -or !$summary.fk_ok){throw 'PRESERVATION_NOT_CONFIRMED'}
 }
 foreach($f in @('digest','schema','admin_count','media_digest')){if($Receipt.before.$f -cne $Receipt.after.$f){throw 'PRESERVATION_NOT_CONFIRMED'}}
 $b=$Receipt.backup
 if(!$b -or $b.file -cnotmatch '^manual-[0-9TZ]+-[0-9a-f]{8}\.db$' -or $b.media_file -cne ($b.file -replace '\.db$','.media.tar') -or $b.sha256 -cnotmatch '^[a-f0-9]{64}$' -or $b.media_sha256 -cnotmatch '^[a-f0-9]{64}$' -or $b.schema -cne '0015_deployment_diagnostics' -or $b.operation_id -cne $ops[0].id){throw 'JOURNAL_INVALID'}
 # Retained recipe bytes connect each receipt to the preceding release; neither
 # the deployment journal nor previous upgrade files are rewritten.
 $saved=(Get-DeployCompose $deployment.id $deployment.old_default).Replace($appImage,$Source)
 foreach($pair in @(@('compose.before.yml',$saved),@('owner.before.txt',('fucheng-vpc-full-v1|'+(Get-VpcHash $saved))))){
  $path=Join-Path $Directory.FullName $pair[0];Assert-VpcNoLink $path;Assert-VpcOwner $path
  if(!(Test-Path -LiteralPath $path -PathType Leaf) -or [IO.File]::ReadAllText($path) -cne $pair[1]){throw 'UNKNOWN_MANAGED_FILES'}
 }
}

function Get-UpgradeSummarySource {
 $sourceText=@'
import hashlib,json,sqlite3,sys
from pathlib import Path
from contextlib import closing
root=Path(sys.argv[1] if len(sys.argv)>1 else '/data')
def canonical(value):
 return json.dumps(value,ensure_ascii=True,separators=(',',':'),default=lambda b:{'bytes':b.hex()}).encode()
try:
 pointer=root/'active.json'
 if pointer.is_symlink():raise ValueError()
 name=json.loads(pointer.read_text())['database']
 if not isinstance(name,str) or Path(name).name!=name or not name.endswith('.db'):raise ValueError()
 path=root/name
 if path.is_symlink() or not path.is_file():raise ValueError()
 with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
  db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
  if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:raise ValueError()
  if db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError()
  if db.execute('SELECT version_num FROM alembic_version').fetchall()!=[('0015_deployment_diagnostics',)]:raise ValueError()
  schema=db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
  digest=hashlib.sha256(canonical(schema))
  tables=db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
  for (table,) in tables:
   quoted='"'+table.replace('"','""')+'"'
   rows=sorted(canonical(row) for row in db.execute('SELECT * FROM '+quoted))
   digest.update(canonical([table,len(rows)]))
   for row in rows:digest.update(len(row).to_bytes(8,'big'));digest.update(row)
  admins=db.execute('SELECT count(*) FROM admins').fetchone()[0]
  if admins<1:raise ValueError()
  media_hash=hashlib.sha256();media=root/'announcement-media'
  if media.is_symlink():raise ValueError()
  if media.exists():
   for p in sorted(media.iterdir()):
    if p.is_symlink() or not p.is_file():raise ValueError()
    media_hash.update(canonical([p.name,p.stat().st_size,hashlib.sha256(p.read_bytes()).hexdigest()]))
  # No rows, usernames, password hashes, paths, or per-table digests leave here.
  print(json.dumps(dict(ok=True,schema='0015_deployment_diagnostics',digest=digest.hexdigest(),admin_count=admins,media_digest=media_hash.hexdigest(),integrity_ok=True,fk_ok=True),separators=(',',':')))
except Exception:
 print('{"ok":false,"error":"READ_ONLY_VERIFY_FAILED"}')
 raise SystemExit(1)
'@
 return $sourceText.Replace("`r`n","`n")
}

function Invoke-UpgradeJob([string]$Name,[string]$Image,[string[]]$Mounts,[string[]]$Command) {
 # Persist intent BEFORE create. A timeout is not evidence that Docker did nothing.
 # No --rm; neither this invocation nor a rerun can resend this operation.
 if(@($journal.operations|Where-Object {$_.name -ceq $Name}).Count){throw 'UPGRADE_RECONCILIATION_REQUIRED'}
 $op=[pscustomobject]@{name=$Name;container=('fucheng-upgrade-'+$journal.id+'-'+$Name);id=$null;status='create_pending';exit_code=$null}
 $journal.operations+=,$op;Save-UpgradeJournal
 $arguments=@('create','--name',$op.container,'--platform','linux/amd64','--pull','never','--network','none','--restart','no','--user','10001:10001','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:size=32m,mode=1777','--label','com.docker.compose.project=fucheng','--label','io.fucheng.vpc.managed=full-v1','--label',('io.fucheng.vpc.deployment='+$deployment.id),'--label',('io.fucheng.vpc.upgrade='+$journal.id),'--label',('io.fucheng.vpc.operation='+$Name),'--entrypoint','python')
 foreach($mount in $Mounts){$arguments+=@('--volume',$mount)}
 if($Name -ceq 'backup'){$arguments+=@('--env',('FUCHENG_IMAGE_REF='+$oldImage),'--env','FUCHENG_BASE_PATH=','--env',('FUCHENG_RESTORE_PUBLIC_ORIGIN='+$origin),'--env','FUCHENG_RESTORE_PROXY_KIND=cloudflare')}
 $id=Invoke-VpcChecked ($arguments+@($Image)+$Command) 30
 if($id -cnotmatch '^[a-f0-9]{64}$'){throw 'OPERATION_UNKNOWN'}
 $op.id=$id;$op.status='start_pending';Save-UpgradeJournal
 $null=Invoke-VpcChecked @('start',$id) 20
 $op.status='running';Save-UpgradeJournal
 for($i=0;$i -lt 45;$i++){
  $state=Invoke-VpcChecked @('inspect','--type','container','--format','{{.State.Status}}|{{.State.ExitCode}}',$id) 5
  if($state -cmatch '^exited\|([0-9]+)$'){
   $op.status='complete';$op.exit_code=[int]$Matches[1];Save-UpgradeJournal
   if($op.exit_code -ne 0){throw 'OPERATION_FAILED'};return $id
  }
  if($state -cnotin @('running|0','created|0')){throw 'OPERATION_UNKNOWN'}
  Start-Sleep -Seconds 2
 }
 throw 'OPERATION_UNKNOWN'
}

function Get-UpgradeSummary([string]$Name,[string]$Image) {
 $id=Invoke-UpgradeJob $Name $Image @('fucheng_data:/data:ro') @('-c',(Get-UpgradeSummarySource))
 # Logs are ONLY requested from our fixed read-only Python summary, never app,
 # backup, cloudflared, or Docker stderr. This command emits no secret material.
 $raw=Invoke-VpcChecked @('logs','--tail','1',$id) 10
 $v=$raw|ConvertFrom-Json
 if($v.ok -isnot [bool] -or !$v.ok -or $v.schema -cne '0015_deployment_diagnostics' -or $v.digest -cnotmatch '^[a-f0-9]{64}$' -or $v.media_digest -cnotmatch '^[a-f0-9]{64}$' -or $v.admin_count -lt 1 -or $v.integrity_ok -isnot [bool] -or !$v.integrity_ok -or $v.fk_ok -isnot [bool] -or !$v.fk_ok){throw 'DATA_VERIFY_FAILED'}
 return $v
}

function Get-UpgradeBackup([string]$Directory,[string]$SourceImage,[string]$OperationId) {
 $files=@(Get-ChildItem -LiteralPath $Directory -Filter 'manual-*.json')
 if($files.Count -ne 1){throw 'BACKUP_GROUP_UNCONFIRMED'}
 Assert-VpcNoLink $files[0].FullName;Assert-VpcOwner $files[0].FullName
 $info=[IO.File]::ReadAllText($files[0].FullName)|ConvertFrom-Json
 if($info.file -cnotmatch '^manual-[0-9TZ]+-[0-9a-f]{8}\.db$' -or $files[0].Name -cne ($info.file -replace '\.db$','.json') -or $info.media_file -cne ($info.file -replace '\.db$','.media.tar') -or $info.revision -cne '0015_deployment_diagnostics' -or $info.integrity -cne 'ok' -or $info.foreign_key_errors -ne 0 -or $info.restore_config.image_ref -cne $SourceImage -or $info.restore_config.base_path -cne '' -or $info.restore_config.public_origin -cne $origin -or $info.restore_config.proxy_kind -cne 'cloudflare'){throw 'BACKUP_METADATA_MISMATCH'}
 foreach($pair in @(@($info.file,$info.sha256),@($info.media_file,$info.media_sha256))){
  $path=Join-Path $Directory $pair[0];Assert-VpcNoLink $path;Assert-VpcOwner $path
  if($pair[1] -cnotmatch '^[a-f0-9]{64}$' -or !(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $pair[1]){throw 'BACKUP_HASH_MISMATCH'}
 }
 return [pscustomobject]@{file=$info.file;sha256=$info.sha256;media_file=$info.media_file;media_sha256=$info.media_sha256;schema=$info.revision;operation_id=$OperationId}
}

function Remove-SupersededUpgradeBackups([object[]]$NewestFirst) {
 $verifiedCount=0
 foreach($receipt in $NewestFirst){
  $directory=Join-Path $backupRoot ('upgrade-'+$receipt.id)
  $backup=$receipt.backup
  $names=@($backup.file,$backup.media_file,($backup.file -replace '\.db$','.json'))
  try{
   $present=@($names | Where-Object {Test-Path -LiteralPath (Join-Path $directory $_)})
   if($present.Count -eq 0 -and $verifiedCount -gt 0){continue}
   $actual=Get-UpgradeBackup $directory $receipt.old_image $receipt.operations[0].id
   foreach($field in @('file','media_file','sha256','media_sha256')){
    if($actual.$field -cne $backup.$field){throw 'BACKUP_RECEIPT_MISMATCH'}
   }
  }catch{
   Write-Warning ('備份輪替略過無法驗證的備份 '+$receipt.id)
   if($verifiedCount -eq 0){return}
   continue
  }
  $verifiedCount++
  if($verifiedCount -le 2){continue}
  try{
   foreach($name in $names){[IO.File]::Delete((Join-Path $directory $name))}
   Write-Host ('已清理舊升級備份 '+$receipt.id+'，收據保留。')
  }catch{
   Write-Warning ('備份輪替未完成 '+$receipt.id)
   return
  }
 }
}

function Stop-UpgradeStack($Stack) {
 foreach($service in @('cloudflared','backup','app')){
  $items=@($Stack|Where-Object {$_.service -ceq $service});if($items.Count -ne 1){throw 'STACK_IDENTITY_MISMATCH'}
  $item=$items[0];$null=Invoke-VpcChecked @('stop','--time','45',$item.id) 55
  if((Invoke-VpcChecked @('inspect','--type','container','--format','{{.State.Status}}',$item.id) 5) -cne 'exited'){throw 'STACK_STOP_UNCONFIRMED'}
 }
 Assert-UpgradeNoWriter
}

function Stop-UpgradeKnownMembers([string]$Ref,[string]$ImageId) {
 # Failure cleanup must not require all three members to exist: Compose may
 # already have started a new writer when another member's create failed.
 $allStopped=$true
 foreach($service in @('cloudflared','backup','app')){
  # Recheck the local endpoint before each stop. A changed/unknown context is
  # not authority to issue even a bounded stop against another Docker engine.
  try{
   if($env:DOCKER_HOST -or $env:DOCKER_CONTEXT -or $env:DOCKER_TLS_VERIFY -or $env:DOCKER_CERT_PATH){throw 'DOCKER_HOST_OVERRIDE'}
   $endpoint=Invoke-VpcChecked @('context','inspect','--format','{{.Endpoints.docker.Host}}')
   if($endpoint -cnotmatch '^npipe:/+\./pipe/(?:docker_engine|dockerDesktopLinuxEngine)$' -or $endpoint -cne $dockerEndpoint){throw 'LOCAL_DOCKER_REQUIRED'}
   if((Invoke-VpcChecked @('info','--format','{{.OSType}}|{{.Architecture}}')) -cnotin @('linux|x86_64','linux|amd64')){throw 'LINUX_AMD64_REQUIRED'}
  }catch{Write-Host '停止環境未確認；保留現場。';return $false}
  try{
   # This is the same complete per-member image/labels/mounts/network/recipe
   # guard used in normal preflight, with only the reviewed old/new pins allowed.
   $item=Assert-UpgradeMember $service $Ref $ImageId $false $true
   $null=Invoke-VpcChecked @('stop','--time','45',$item.id) 55
   if((Invoke-VpcChecked @('inspect','--type','container','--format','{{.State.Status}}',$item.id) 5) -cne 'exited'){throw 'STACK_STOP_UNCONFIRMED'}
  }catch{
   # Missing, foreign or unconfirmed members remain untouched. Continue to
   # stop other independently verified writers; never report group success.
   $allStopped=$false;Write-Host ('成員停止未確認：fucheng-'+$service+'；保留該成員並繼續核對其他成員。')
  }
 }
 # Shared-resource/project checks run after the independent stops so an
 # unknown resource cannot keep a known writer running or become group success.
 try{$null=Assert-UpgradeIdentity $Ref $ImageId $false $true;Assert-UpgradeNoWriter}catch{$allStopped=$false}
 return $allStopped
}

function Invoke-ClubUpgrade([string]$TargetImage,[string]$ExpectedImageId) {
 $docker=$null;$lock=$null;$journal=$null;$priorUpgrade=$null;$intermediateUpgrade=$null;$deployment=$null;$stack=$null;$writePhase=$false;$done=$false;$stage='preflight';$upgradeJournalPath=$null
 try{
  Assert-VpcWindows
  if($TargetImage -cnotmatch '^momonong/fucheng-players-system@sha256:[a-f0-9]{64}$' -or $ExpectedImageId -cnotmatch '^sha256:[a-f0-9]{64}$' -or $TargetImage -cin @($oldImage,$originalImage,$v140Image) -or $ExpectedImageId -cin @($oldImageId,$originalImageId,$v140ImageId)){throw 'TARGET_PIN_REQUIRED'}
  if($env:DOCKER_HOST -or $env:DOCKER_CONTEXT -or $env:DOCKER_TLS_VERIFY -or $env:DOCKER_CERT_PATH){throw 'DOCKER_HOST_OVERRIDE'}
  $root=Get-UpgradeRoot;Assert-VpcNoLink $root;Assert-VpcOwner $root
  $composePath=Join-Path $root 'compose.yml';$markerPath=Join-Path $root 'owner.txt';$deployJournalPath=Join-Path $root 'deploy-journal.json';$backupRoot=Join-Path $root 'backup'
  foreach($p in @($composePath,$markerPath,$deployJournalPath,(Join-Path $root 'setup.lock'),(Join-Path $root 'protected.env'),(Join-Path $root 'turnstile.secret'),(Join-Path $root 'tunnel.token'),$backupRoot,(Join-Path $backupRoot 'live'))){Assert-VpcNoLink $p;Assert-VpcOwner $p}
  $lock=[IO.File]::Open((Join-Path $root 'setup.lock'),[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
  if(Test-Path -LiteralPath ($deployJournalPath+'.next')){throw 'JOURNAL_UPDATE_PENDING'}
  $deployment=[IO.File]::ReadAllText($deployJournalPath)|ConvertFrom-Json
  if($deployment.version -ne 1 -or $deployment.phase -cne 'COMPLETE' -or $deployment.id -cnotmatch '^[a-f0-9]{32}$' -or $deployment.source_id -cnotmatch '^[a-f0-9]{64}$' -or !(Test-UpgradeImageIdentity $deployment.image_id $originalImage $originalImageId) -or $deployment.target_volume -cne 'fucheng_data' -or $deployment.old_default -isnot [bool]){throw 'JOURNAL_INVALID'}
  foreach($f in @('business_match','admin_match','media_match')){if($deployment.verification.$f -isnot [bool] -or !$deployment.verification.$f){throw 'PRESERVATION_NOT_CONFIRMED'}}
  # Root pending files are checked before any Docker call, even when no new
  # journal exists yet. Never overwrite a previous process's staged recipe.
  if(@(Get-ChildItem -LiteralPath $root -File|Where-Object {$_.Name -clike '*.next' -or $_.Name -clike '*.upgrade-next'}).Count){throw 'JOURNAL_UPDATE_PENDING'}
  $upgrades=@(Get-ChildItem -LiteralPath $backupRoot -Directory -Filter 'upgrade-*')
  if($upgrades.Count -lt 1 -or $upgrades.Count -gt 3){throw 'UPGRADE_RECONCILIATION_REQUIRED'}
  $priorUpgrade=$null;$targetUpgrade=$null
  foreach($directory in $upgrades){
   Assert-VpcNoLink $directory.FullName;Assert-VpcOwner $directory.FullName
   if(@(Get-ChildItem -LiteralPath $directory.FullName -File|Where-Object {$_.Name -clike '*.next' -or $_.Name -clike '*.upgrade-next'}).Count){throw 'JOURNAL_UPDATE_PENDING'}
   $path=Join-Path $directory.FullName 'upgrade-journal.json'
   if(!(Test-Path -LiteralPath $path -PathType Leaf)){throw 'UPGRADE_RECONCILIATION_REQUIRED'}
   Assert-VpcNoLink $path;Assert-VpcOwner $path
   $receipt=[IO.File]::ReadAllText($path)|ConvertFrom-Json
   if($receipt.phase -cne 'COMPLETE'){throw 'UPGRADE_RECONCILIATION_REQUIRED'}
   if($receipt.old_image -ceq $originalImage -and $receipt.target_image -ceq $oldImage){
    if($priorUpgrade){throw 'UPGRADE_RECONCILIATION_REQUIRED'}
    Assert-UpgradeCompletedReceipt $receipt $directory $originalImage $originalImageId $oldImage $oldImageId
    $priorUpgrade=$receipt
   }elseif($receipt.old_image -ceq $oldImage -and $receipt.target_image -ceq $v140Image){
    if($intermediateUpgrade){throw 'UPGRADE_RECONCILIATION_REQUIRED'}
    Assert-UpgradeCompletedReceipt $receipt $directory $oldImage $oldImageId $v140Image $v140ImageId
    $intermediateUpgrade=$receipt
   }elseif($receipt.old_image -cin @($oldImage,$v140Image) -and $receipt.target_image -ceq $TargetImage){
    if($targetUpgrade){throw 'UPGRADE_RECONCILIATION_REQUIRED'}
    $targetUpgrade=$receipt;$checkpointDir=$directory.FullName;$upgradeJournalPath=$path
   }else{throw 'JOURNAL_INVALID'}
  }
  if(!$priorUpgrade){throw 'UPGRADE_RECONCILIATION_REQUIRED'}
  $previousReceipt=$priorUpgrade
  if($intermediateUpgrade){
   if($intermediateUpgrade.previous_upgrade_id -cne $priorUpgrade.id){throw 'JOURNAL_INVALID'}
   $previousReceipt=$intermediateUpgrade
   $oldImage=$v140Image
   $oldImageId=$v140ImageId
  }
  if($targetUpgrade){
   if($targetUpgrade.previous_upgrade_id -cne $previousReceipt.id){throw 'JOURNAL_INVALID'}
   Assert-UpgradeCompletedReceipt $targetUpgrade (Get-Item -LiteralPath $checkpointDir) $oldImage $oldImageId $TargetImage $ExpectedImageId
   $journal=$targetUpgrade
  }
  $oldCompose=(Get-DeployCompose $deployment.id $deployment.old_default).Replace($appImage,$oldImage)
  # Historical receipts preserve the exact old recipe with eight weekly backups.
  if(([regex]::Matches($oldCompose,[regex]::Escape($oldImage))).Count -ne 2 -or
     ([regex]::Matches($oldCompose,'FUCHENG_BACKUP_KEEP: "8"')).Count -ne 1){throw 'UNKNOWN_MANAGED_FILES'}
  $newCompose=$oldCompose.Replace($oldImage,$TargetImage).Replace('FUCHENG_BACKUP_KEEP: "8"','FUCHENG_BACKUP_KEEP: "2"')
  $expectedCompose=if($journal){$newCompose}else{$oldCompose}
  $compose=[IO.File]::ReadAllText($composePath);$marker=[IO.File]::ReadAllText($markerPath)
  if($compose -cne $expectedCompose -or $marker -cne ('fucheng-vpc-full-v1|'+(Get-VpcHash $compose))){throw 'UNKNOWN_MANAGED_FILES'}
  $tool=Get-Command docker.exe -CommandType Application -ErrorAction Stop|Select-Object -First 1;$docker=$tool.Source
  $dockerEndpoint=Invoke-VpcChecked @('context','inspect','--format','{{.Endpoints.docker.Host}}')
  if($dockerEndpoint -cnotmatch '^npipe:/+\./pipe/(?:docker_engine|dockerDesktopLinuxEngine)$'){throw 'LOCAL_DOCKER_REQUIRED'}
  if((Invoke-VpcChecked @('info','--format','{{.OSType}}|{{.Architecture}}')) -cnotin @('linux|x86_64','linux|amd64')){throw 'LINUX_AMD64_REQUIRED'}
  $tunnelImageId=Invoke-VpcChecked @('image','inspect','--format','{{.Id}}',$tunnelImage)
  if($tunnelImageId -cnotmatch '^sha256:[a-f0-9]{64}$'){throw 'STACK_IDENTITY_MISMATCH'}
  if($journal){
   if(!(Test-UpgradeImageIdentity (Invoke-VpcChecked @('image','inspect','--format','{{.Id}}',$TargetImage)) $TargetImage $ExpectedImageId)){throw 'TARGET_IMAGE_MISMATCH'}
   $stack=Assert-UpgradeIdentity $TargetImage $ExpectedImageId $true;Assert-UpgradeNoWriter @($stack|Where-Object {$_.service -cin @('app','backup')}|ForEach-Object {$_.id})
   if(!(Test-DeployPublic)){throw 'PUBLIC_HEALTH_UNCONFIRMED'}
   $retentionReceipts=@($journal)
   if($intermediateUpgrade){$retentionReceipts+=@($intermediateUpgrade)}
   $retentionReceipts+=@($priorUpgrade)
   Remove-SupersededUpgradeBackups $retentionReceipts
   Write-Host 'COMPLETE：既有目標映像身份與公開健康通過；未重新備份或重建。';return
  }
  if(!(Test-UpgradeImageIdentity (Invoke-VpcChecked @('image','inspect','--format','{{.Id}}',$oldImage)) $oldImage $oldImageId)){throw 'JOURNAL_IMAGE_MISMATCH'}
  $stack=Assert-UpgradeIdentity $oldImage $oldImageId $true
  Assert-UpgradeNoWriter @($stack|Where-Object {$_.service -cin @('app','backup')}|ForEach-Object {$_.id})
  $stage='download_target';$null=Invoke-VpcChecked @('pull','--platform','linux/amd64',$TargetImage) 300
  if(!(Test-UpgradeImageIdentity (Invoke-VpcChecked @('image','inspect','--format','{{.Id}}',$TargetImage)) $TargetImage $ExpectedImageId)){throw 'TARGET_IMAGE_MISMATCH'}
  # Recheck after a potentially long download, before changing the running stack.
  $stack=Assert-UpgradeIdentity $oldImage $oldImageId $true
  Assert-UpgradeNoWriter @($stack|Where-Object {$_.service -cin @('app','backup')}|ForEach-Object {$_.id})
  $id=[Guid]::NewGuid().ToString('N');$checkpointDir=Join-Path $backupRoot ('upgrade-'+$id)
  Assert-VpcNoLink $checkpointDir;if(Test-Path -LiteralPath $checkpointDir){throw 'EXISTING_BACKUP_TARGET'}
  $null=New-Item -ItemType Directory -Path $checkpointDir;Set-VpcPrivatePath $checkpointDir $true;Assert-VpcOwner $checkpointDir
  $upgradeJournalPath=Join-Path $checkpointDir 'upgrade-journal.json'
  $journal=[pscustomobject]@{version=1;id=$id;deployment_id=$deployment.id;previous_upgrade_id=$previousReceipt.id;old_image=$oldImage;old_image_id=$oldImageId;target_image=$TargetImage;target_image_id=$ExpectedImageId;phase='PREPARED';operations=@();backup=$null;before=$null;after=$null;failure_code=$null;stop_confirmed=$null}
  Write-UpgradeFile (Join-Path $checkpointDir 'compose.before.yml') $compose
  Write-UpgradeFile (Join-Path $checkpointDir 'owner.before.txt') $marker
  Save-UpgradeJournal
  $stage='stop_old';Set-UpgradePhase 'STOP_PENDING';$writePhase=$true
  Stop-UpgradeStack $stack;Set-UpgradePhase 'STOP_CONFIRMED'
  $stage='backup';Set-UpgradePhase 'BACKUP_PENDING'
  $null=Invoke-UpgradeJob 'backup' $oldImage @('fucheng_data:/data',($checkpointDir+':/backups')) @('/app/runtime.py','backup')
  $journal.backup=Get-UpgradeBackup $checkpointDir $oldImage $journal.operations[0].id;Set-UpgradePhase 'BACKUP_CONFIRMED'
  $stage='before_summary';$journal.before=Get-UpgradeSummary 'before' $oldImage;Set-UpgradePhase 'BEFORE_CONFIRMED'
  Assert-UpgradeNoWriter
  $stage='switch_recipe';Set-UpgradePhase 'RECIPE_PENDING'
  # Write-through staging plus replace keeps the original private ACL. Recovery
  # always uses the retained original files; no automatic rollback is attempted.
  foreach($pair in @(@($composePath,$newCompose),@($markerPath,('fucheng-vpc-full-v1|'+(Get-VpcHash $newCompose))))){
   $next=$pair[0]+'.upgrade-next';if(Test-Path -LiteralPath $next){throw 'JOURNAL_UPDATE_PENDING'}
   Write-UpgradeFile $next $pair[1];[IO.File]::Replace($next,$pair[0],[System.Management.Automation.Language.NullString]::Value)
  }
  if([IO.File]::ReadAllText($composePath) -cne $newCompose -or [IO.File]::ReadAllText($markerPath) -cne ('fucheng-vpc-full-v1|'+(Get-VpcHash $newCompose))){throw 'UNKNOWN_MANAGED_FILES'}
  Set-UpgradePhase 'RECIPE_CONFIRMED'
  $composeArgs=@('compose','--project-name','fucheng','--env-file',(Join-Path $root 'protected.env'),'--file',$composePath)
  $stage='start_app_backup';Set-UpgradePhase 'APP_BACKUP_PENDING'
  $null=Invoke-VpcChecked ($composeArgs+@('up','--detach','--no-build','--pull','never','--wait','--wait-timeout','120','app','backup')) 135
  $stack=Assert-UpgradeIdentity $TargetImage $ExpectedImageId $false;Assert-DeployHealthy
  # Connector must still be stopped throughout both private startup and readback.
  $connector=@($stack|Where-Object {$_.service -ceq 'cloudflared'})[0]
  if((Invoke-VpcChecked @('inspect','--format','{{.State.Status}}',$connector.id)) -cne 'exited'){throw 'CONNECTOR_NOT_STOPPED'}
  Assert-UpgradeNoWriter @($stack|Where-Object {$_.service -cin @('app','backup')}|ForEach-Object {$_.id})
  $stage='after_summary';$journal.after=Get-UpgradeSummary 'after' $TargetImage
  foreach($f in @('digest','schema','admin_count','media_digest')){if($journal.before.$f -cne $journal.after.$f){throw 'DATA_CHANGED_REVIEW_REQUIRED'}}
  Set-UpgradePhase 'DATA_UNCHANGED'
  $stage='start_connector';Set-UpgradePhase 'CONNECTOR_PENDING'
  $null=Invoke-VpcChecked ($composeArgs+@('up','--detach','--no-build','--pull','never','--no-deps','cloudflared')) 30
  $stack=Assert-UpgradeIdentity $TargetImage $ExpectedImageId $true
  $stage='public_health';$passed=$false
  for($i=0;$i -lt 8;$i++){if(Test-DeployPublic){$passed=$true;break};if($i -lt 7){Start-Sleep -Seconds 3}}
  if(!$passed){throw 'PUBLIC_HEALTH_UNCONFIRMED'}
  Assert-DeployHealthy $true
  $journal.stop_confirmed=$null;Set-UpgradePhase 'COMPLETE';$done=$true
  $retentionReceipts=@($journal)
  if($intermediateUpgrade){$retentionReceipts+=@($intermediateUpgrade)}
  $retentionReceipts+=@($priorUpgrade)
  Remove-SupersededUpgradeBackups $retentionReceipts
  Write-Host ('COMPLETE：1.4.1 更新完成；資料、媒體與 '+[int]$journal.after.admin_count+' 個管理員帳號核對一致。')
  Write-Host 'https://fucheng.momonong.workers.dev/；請沿用球館原帳密登入。'
  Write-Host ('備份及操作收據：'+$checkpointDir)
 }catch{
  $safe=@('WINDOWS_CONSOLE_REQUIRED','TARGET_PIN_REQUIRED','DOCKER_HOST_OVERRIDE','PRIVATE_ACL_UNCONFIRMED','LINKED_PATH','JOURNAL_UPDATE_PENDING','JOURNAL_INVALID','PRESERVATION_NOT_CONFIRMED','UPGRADE_RECONCILIATION_REQUIRED','UNKNOWN_MANAGED_FILES','LOCAL_DOCKER_REQUIRED','LINUX_AMD64_REQUIRED','STACK_IDENTITY_MISMATCH','STACK_UNHEALTHY','UNKNOWN_FUCHENG_RESOURCE','OTHER_TARGET_WRITER','JOURNAL_IMAGE_MISMATCH','TARGET_IMAGE_MISMATCH','EXISTING_BACKUP_TARGET','STACK_STOP_UNCONFIRMED','DOCKER_COMMAND_UNCONFIRMED','OPERATION_UNKNOWN','OPERATION_FAILED','BACKUP_GROUP_UNCONFIRMED','BACKUP_METADATA_MISMATCH','BACKUP_HASH_MISMATCH','DATA_VERIFY_FAILED','DATA_CHANGED_REVIEW_REQUIRED','CONNECTOR_NOT_STOPPED','PUBLIC_HEALTH_UNCONFIRMED')
  $code=if($_.Exception.Message -cin $safe){$_.Exception.Message}else{'UNCLASSIFIED'}
  # Stop only freshly rechecked owned stack members. Unknown stop never starts
  # anything, never changes image back, and never clears the operation receipt.
  if($writePhase -and !$done){
   $stopped=$false
   try{
    $stopped=Stop-UpgradeKnownMembers $TargetImage $ExpectedImageId
    if(!$stopped){Write-Host '停止未完全確認；已核對成員已逐一嘗試停寫，保留現場，未啟動任何舊站。'}
   }catch{Write-Host '停止未完全確認；保留現場，未啟動任何舊站。'}
   if($journal){$journal.failure_code=$code;$journal.stop_confirmed=$stopped;try{Save-UpgradeJournal}catch{Write-Host 'journal 更新未確認；保留原收據與 .next，不可直接重跑。'}}
  }
  Write-Host ('停止：stage='+$stage+'；code='+$code)
  Write-Host '原資料卷、帳號、備份與所有操作容器均保留；網站可能保持停止。請回傳上述階段及代碼，核對原收據後再處理；勿直接重跑、重貼首次安裝碼或手動還原。'
 }finally{if($lock){$lock.Dispose()}}
}

if($MyInvocation.InvocationName -ne '.') {Invoke-ClubUpgrade $TargetImage $ExpectedImageId}
