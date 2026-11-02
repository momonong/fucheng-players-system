& {
# Windows PowerShell 5.1; connector only. No app, database, service or firewall changes.
$ErrorActionPreference='Stop';$utf8=New-Object Text.UTF8Encoding($false)
$tunnelId='fa458cdb-0bf4-43a2-89ef-e9d15b348d14';$image='cloudflare/cloudflared@sha256:faa8e0a1475f137c910be6025f43c8e4092fdd35461b31e19fd1390657a1ff39'
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
function Assert-VpcOwner([string]$Path) {if((Get-Acl -LiteralPath $Path).GetOwner([Security.Principal.SecurityIdentifier]) -ne [Security.Principal.WindowsIdentity]::GetCurrent().User){throw 'UNKNOWN_OWNER'}}
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
function Assert-VpcResources([bool]$Managed,[string]$ComposePath) {
 foreach($kind in @('container','network','volume')){
  $format=if($kind -eq 'container'){'{{.ID}}|{{.Names}}|{{.Label "com.docker.compose.project"}}|{{.Label "io.fucheng.vpc.managed"}}|{{.Label "com.docker.compose.project.config_files"}}'}elseif($kind -eq 'network'){'{{.ID}}|{{.Name}}|{{.Label "com.docker.compose.project"}}|{{.Label "io.fucheng.vpc.managed"}}'}else{'{{.Name}}|{{.Label "com.docker.compose.project"}}'}
  $command=@($kind,'ls');if($kind -eq 'container'){$command+=@('-a','--no-trunc')};$lines=Invoke-VpcChecked ($command+@('--format',$format))
  foreach($line in @($lines -split "`r?`n"|Where-Object {$_})){
   $f=$line.Split('|');$name=if($kind -eq 'volume'){$f[0]}else{$f[1]};$project=if($kind -eq 'volume'){$f[1]}else{$f[2]}
   $clash=($project -ceq 'fucheng' -or $name -cmatch '^fucheng(?:$|_|-cloudflared$|-[a-z0-9]+-[0-9]+$)');if(!$clash){continue}
   if(!$Managed -or $kind -eq 'volume' -or $project -cne 'fucheng' -or $f[3] -cne 'tunnel-only-v1'){throw 'UNKNOWN_FUCHENG_RESOURCE'}
   if($kind -eq 'container' -and ($name -cne 'fucheng-cloudflared' -or [IO.Path]::GetFullPath($f[4]) -ine $ComposePath)){throw 'UNKNOWN_FUCHENG_RESOURCE'}
   if($kind -eq 'network' -and $name -cne 'fucheng_default'){throw 'UNKNOWN_FUCHENG_RESOURCE'}
  }
 }
}
$compose=@'
name: fucheng
services:
  cloudflared:
    image: IMAGE
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
$compose=$compose.Replace('IMAGE',$image);$lock=$null;$docker=$null;$plain=$null;$secret=$null
$stage='preflight'
try{
 Assert-VpcWindows;if($env:DOCKER_HOST){throw 'DOCKER_HOST_OVERRIDE'};$local=[Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData);if(!$local -or ![IO.Path]::IsPathRooted($local)){throw 'LOCAL_DIRECTORY'}
 $root=Join-Path $local 'Fucheng';$path=Join-Path $root 'compose.yml';$marker=Join-Path $root 'owner.txt';$tokenPath=Join-Path $root 'tunnel.token';Assert-VpcNoLink $root
 $owned='fucheng-vpc-tunnel-only-v1|'+(Get-VpcHash $compose);$managed=Test-Path -LiteralPath $root
 if($managed){Assert-VpcOwner $root;foreach($item in @(Get-ChildItem -LiteralPath $root -Force)){Assert-VpcNoLink $item.FullName;if($item.PSIsContainer -or $item.Name -cnotin @('owner.txt','compose.yml','tunnel.token','setup.lock')){throw 'UNKNOWN_DIRECTORY_CONTENT'};Assert-VpcOwner $item.FullName};if(!(Test-Path -LiteralPath $marker -PathType Leaf) -or [IO.File]::ReadAllText($marker) -cne $owned -or !(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-VpcHash ([IO.File]::ReadAllText($path))) -cne (Get-VpcHash $compose)){throw 'UNKNOWN_MANAGED_FILES'}}
 $tool=Get-Command 'docker.exe' -CommandType Application -ErrorAction SilentlyContinue|Select-Object -First 1;if(!$tool){throw 'DOCKER_MISSING'};$docker=$tool.Source
 if((Invoke-VpcChecked @('context','inspect','--format','{{.Endpoints.docker.Host}}')) -cnotmatch '^npipe:/+\./pipe/(?:docker_engine|dockerDesktopLinuxEngine)$'){throw 'LOCAL_DOCKER_REQUIRED'}
 if((Invoke-VpcChecked @('info','--format','{{.OSType}}|{{.Architecture}}')) -cnotin @('linux|x86_64','linux|amd64')){throw 'LINUX_AMD64_REQUIRED'};$null=Invoke-VpcChecked @('compose','version','--short')
 $stage='ownership';Assert-VpcResources $managed $path
 if(!$managed){$null=New-Item -ItemType Directory -Path $root -ErrorAction Stop};Assert-VpcNoLink $root;Set-VpcPrivatePath $root $true
 $lock=[IO.File]::Open((Join-Path $root 'setup.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
 if(!$managed){[IO.File]::WriteAllText($path,$compose,$utf8);[IO.File]::WriteAllText($marker,$owned,$utf8)}
 $stage='token'
 if(Test-Path -LiteralPath $tokenPath -PathType Leaf){Assert-VpcNoLink $tokenPath;Assert-VpcOwner $tokenPath;Set-VpcPrivatePath $tokenPath $false;$plain=[IO.File]::ReadAllText($tokenPath);Assert-VpcToken $plain;$plain=$null;Write-Host '沿用已保存的專用 Tunnel token。'}else{
  $bytes=$null;$secret=Read-Host '請貼上 fucheng Tunnel token 或 Cloudflare 複製的整條 Docker 命令（隱藏輸入；不要傳到聊天）' -AsSecureString;$bstr=[IntPtr]::Zero
  try{$bstr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret);$plain=Convert-VpcTokenInput ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr));Assert-VpcToken $plain;$file=[IO.File]::Open($tokenPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);try{Set-VpcPrivatePath $tokenPath $false;$bytes=$utf8.GetBytes($plain);$file.Write($bytes,0,$bytes.Length)}finally{if($bytes){[Array]::Clear($bytes,0,$bytes.Length)};$file.Dispose()}}finally{if($bstr -ne [IntPtr]::Zero){[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)};$plain=$null;if($secret){$secret.Dispose();$secret=$null}}
 }
 $stage='image';$r=Invoke-ProbeDocker @('image','inspect','--format','{{.Os}}|{{.Architecture}}',$image) 10
 if($r.timed_out){throw 'IMAGE_UNKNOWN'};if($r.exit_code -ne 0){Write-Host '下載固定版本 cloudflared image…';$null=Invoke-VpcChecked @('pull','--platform','linux/amd64',$image) 180}
 if((Invoke-VpcChecked @('image','inspect','--format','{{.Os}}|{{.Architecture}}',$image)) -cne 'linux|amd64'){throw 'IMAGE_UNCONFIRMED'}
 $stage='start';Assert-VpcResources $true $path;$since=(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
 $null=Invoke-VpcChecked @('compose','--project-directory',$root,'--project-name','fucheng','--file',$path,'up','--detach','--no-build','--pull','never','--no-recreate','cloudflared') 30
 $stage='registration';$registered=$false;$http2=$false
 for($i=0;$i -lt 12;$i++){$r=Invoke-ProbeDocker @('logs','--since',$since,'--tail','50','fucheng-cloudflared') 3;if($r.exit_code -eq 0 -and !$r.timed_out){$logs=$r.stdout+"`n"+$r.stderr;$registered=$logs -cmatch 'Registered tunnel connection\b[^\r\n]*\bprotocol=quic(?:\s|$)';$http2=$logs -cmatch 'Registered tunnel connection\b[^\r\n]*\bprotocol=http2(?:\s|$)';$logs=$null};if($registered -or $http2){break};if($i -lt 11){Start-Sleep -Seconds 2}}
 $state=Invoke-VpcChecked @('inspect','--type','container','--format','{{.State.Status}}','fucheng-cloudflared') 5
 $safeState=if($state -cin @('created','running','paused','restarting','removing','exited','dead')){$state}else{'unknown'};$status=if($http2){'UNEXPECTED_HTTP2'}elseif($registered){'QUIC_REGISTERED_OBSERVED'}else{'QUIC_NOT_OBSERVED'}
 Write-Host ('fucheng connector：'+$safeState+'；'+$status+'。最近約 60 秒內觀察，不等於目前連線健康。')
 Write-Host '本段只啟動專用 Tunnel；未部署 app、未操作現有資料庫。Worker／Service／網站端到端尚未驗證。'
 Write-Host '固定 Worker：https://fucheng.momonong.workers.dev；私有工具位置：%LOCALAPPDATA%\Fucheng。'
}catch{
 $allowed=@('WINDOWS_CONSOLE_REQUIRED','DOCKER_HOST_OVERRIDE','LOCAL_DIRECTORY','LINKED_PATH','UNKNOWN_OWNER','UNKNOWN_DIRECTORY_CONTENT','UNKNOWN_MANAGED_FILES','DOCKER_MISSING','LOCAL_DOCKER_REQUIRED','LINUX_AMD64_REQUIRED','UNKNOWN_FUCHENG_RESOURCE','INVALID_TOKEN','INVALID_TOKEN_INPUT','DOCKER_COMMAND_UNCONFIRMED','IMAGE_UNKNOWN','IMAGE_UNCONFIRMED')
 $code=if($_.Exception.Message -cin $allowed){$_.Exception.Message}else{'UNCLASSIFIED'}
 Write-Host ('停止：stage='+$stage+'; code='+$code+'; type='+$_.Exception.GetType().Name+'。請回報這行狀態；token 留在你的電腦。')
}
finally{$plain=$null;if($secret){$secret.Dispose()};if($lock){$lock.Dispose()}}
}
