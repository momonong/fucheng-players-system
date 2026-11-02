& {
# Complete inline diagnostic, Windows PowerShell 5.1; no permanent policy change.
$ErrorActionPreference='Stop';$utf8=New-Object Text.UTF8Encoding($false)
$appImage='momonong/fucheng-players-system@sha256:0e5a297b0d16876fa56e1b9bed0470c3b8632d55ded6b23ffc5c18315f39e6e2'
$tunnelImage='cloudflare/cloudflared@sha256:faa8e0a1475f137c910be6025f43c8e4092fdd35461b31e19fd1390657a1ff39'
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
function Remove-ProbeResources($State) {
 $ok=$true
 foreach($item in @(@('container',[string]$State.tunnel),@('container',[string]$State.probe),@('network',[string]$State.network))){
  $kind=$item[0];$name=$item[1]
  $label=if($kind -eq 'container'){'{{.Id}}|{{index .Config.Labels "io.fucheng.feasibility.run"}}|{{index .Config.Labels "io.fucheng.feasibility.kind"}}'}else{'{{.Id}}|{{index .Labels "io.fucheng.feasibility.run"}}|{{index .Labels "io.fucheng.feasibility.kind"}}'}
  $r=Invoke-ProbeDocker @('inspect','--type',$kind,'--format',$label,$name) 8
  if($r.exit_code -ne 0 -or $r.timed_out){
   $args=if($kind -eq 'container'){@('container','ls','-a','--no-trunc','--filter',('name='+$name),'--format','{{.ID}}')}else{@('network','ls','--no-trunc','--filter',('name='+$name),'--format','{{.ID}}')}
   $absent=Invoke-ProbeDocker $args 8
   if($absent.exit_code -ne 0 -or $absent.timed_out -or $absent.stdout){$ok=$false};continue
  }
  $fields=$r.stdout.Split('|')
  if($fields.Count -ne 3 -or $fields[0] -cnotmatch '^[0-9a-f]{64}$' -or $fields[1] -cne $State.run_id -or $fields[2] -cne 'nonce-only-v1'){$ok=$false;continue}
  $args=if($kind -eq 'container'){@('container','rm','--force',$fields[0])}else{@('network','rm',$fields[0])}
  $removed=Invoke-ProbeDocker $args 8
  if($removed.exit_code -ne 0 -or $removed.timed_out){$ok=$false}
 }
 return $ok
}
function Start-ProbeWatchdog($State,[string]$Directory) {
 # Independent hidden process survives parent Ctrl+C; no service/task is installed.
 $source="`$ErrorActionPreference='Stop';`$docker='"+$docker.Replace("'","''")+"';`$s='"+(($State|ConvertTo-Json -Compress).Replace("'","''"))+"'|ConvertFrom-Json;"
 foreach($name in @('Stop-OwnedProcessTree','Quote-ProbeArgument','Invoke-ProbeDocker','Remove-ProbeResources')){$source+="`nfunction $name {"+(Get-Command $name).Definition+"}`n"}
 $source+="Start-Sleep -Seconds 480;`$null=Remove-ProbeResources `$s"
 $path=Join-Path $Directory ('watchdog-'+[Guid]::NewGuid().ToString('N')+'.ps1');[IO.File]::WriteAllText($path,$source,(New-Object Text.UTF8Encoding($true)))
 $command="& '"+$path.Replace("'","''")+"'"
 $info=New-Object Diagnostics.ProcessStartInfo;$info.FileName=(Get-Process -Id $PID).Path
 $info.Arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand '+[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
 $info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
 $p=New-Object Diagnostics.Process;$p.StartInfo=$info;[void]$p.Start();$p.StandardInput.Close();$null=$p.StandardOutput.ReadToEndAsync();$null=$p.StandardError.ReadToEndAsync();return $p
}
function Get-NonceServerSource {
 return @'
import http.server,json,os,threading
nonce=os.environ['FUCHENG_PROBE_NONCE']
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  if self.path!='/probe/'+nonce:
   self.send_error(404);return
  body=json.dumps({'nonce':nonce},separators=(',',':')).encode()
  self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
threading.Timer(420,lambda:os._exit(0)).start()
http.server.HTTPServer(('0.0.0.0',8080),Handler).serve_forever()
'@
}
function Get-ProbeUrl([string]$Logs) {
 $matches=[regex]::Matches($Logs,'(?<![A-Za-z0-9./-])https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com(?=[\s|]|$)')
 if($matches.Count){return $matches[0].Value};return $null
}
function Assert-NoToolLink([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            if ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'linked path' }
        }
        $parent = [IO.Path]::GetDirectoryName($current)
        if ($parent -ceq $current) { break }; $current = $parent
    }
}
function Set-ToolPrivateDirectory([string]$Path) {
    if ($env:OS -eq 'Windows_NT') {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
        $acl = New-Object Security.AccessControl.DirectorySecurity
        $acl.SetOwner($identity); $acl.SetAccessRuleProtection($true,$false)
        foreach ($sid in @($identity,(New-Object Security.Principal.SecurityIdentifier('S-1-5-18')),(New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))) {
            [void]$acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow')))
        }
        Set-Acl -LiteralPath $Path -AclObject $acl
    } else { [IO.File]::SetUnixFileMode($Path,[IO.UnixFileMode]::UserRead -bor [IO.UnixFileMode]::UserWrite -bor [IO.UnixFileMode]::UserExecute) }
}
function Get-DiagError([Exception]$Exception) {
 $chain=@();$category='transport';$e=$Exception
 for($i=0;$e -and $i -lt 6;$i++){
  $item=[ordered]@{type=$e.GetType().FullName;hresult=[int]$e.HResult}
  if($e -is [Net.Sockets.SocketException]){$item.socket_code=[int]$e.SocketErrorCode;if($e.SocketErrorCode -in @([Net.Sockets.SocketError]::HostNotFound,[Net.Sockets.SocketError]::TryAgain,[Net.Sockets.SocketError]::NoData)){$category='dns'}}
  if($e -is [Net.WebException]){$item.web_status=[int]$e.Status;if($e.Status -in @([Net.WebExceptionStatus]::TrustFailure,[Net.WebExceptionStatus]::SecureChannelFailure)){$category='tls'};if($e.Status -eq [Net.WebExceptionStatus]::NameResolutionFailure){$category='dns'}}
  if($e -is [Security.Authentication.AuthenticationException]){$category='tls'}
  if($e -is [TimeoutException] -or $e -is [Threading.Tasks.TaskCanceledException]){$category='timeout'}
  $chain+=$item;$e=$e.InnerException
 }
 return @{category=$category;chain=$chain}
}
function Classify-DiagHttp([int]$Status,[byte[]]$Body,[string]$Nonce,[bool]$Cloudflare) {
 $truncated=$Body.Length -gt 16384;if($truncated){$Body=$Body[0..16383]};$text=[Text.Encoding]::UTF8.GetString($Body)
 $r=[ordered]@{http_status=$Status;cloudflare_edge=$Cloudflare;cf_error_code=$null;json_valid=$false;nonce_match=$false;body_truncated=$truncated;outcome=('HTTP_'+$Status)}
 if($Status -ge 300 -and $Status -lt 400){$r.outcome='REDIRECT_REFUSED'}
 if($Cloudflare -and $Status -ge 400){$plain=[regex]::Replace($text,'<[^>]{0,300}>',' ');$m=[regex]::Match($plain,'(?i)\berror(?:\s+code)?\s*[:=]?\s*(1[0-9]{3})\b');if($m.Success){$r.cf_error_code=[int]$m.Groups[1].Value}}
 if($Status -eq 200){try{$v=$text|ConvertFrom-Json;$r.json_valid=$true;$names=@($v.PSObject.Properties.Name);$r.nonce_match=($names.Count -eq 1 -and $names[0] -ceq 'nonce' -and $v.nonce -is [string] -and $v.nonce -ceq $Nonce);$r.outcome=if($r.nonce_match){'NONCE_OK'}else{'NONCE_MISMATCH'}}catch{$r.outcome='NON_JSON'}}
 return $r
}
function Complete-DiagTask($Task,$Clock) {
 $remaining=8000-[int]$Clock.ElapsedMilliseconds
 if($remaining -le 0 -or !$Task.Wait($remaining)){throw (New-Object TimeoutException('DEADLINE'))}
 return $Task.GetAwaiter().GetResult()
}
function Invoke-DiagHttps([string]$Origin,[string]$Nonce) {
 if($Origin -cnotmatch '^https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com$'){throw 'ORIGIN_INVALID'}
 $c=$null;$response=$null;$stream=$null;$old=[Net.ServicePointManager]::SecurityProtocol;$clock=[Diagnostics.Stopwatch]::StartNew()
 $r=@{http_status=$null;outcome='TRANSPORT_ERROR';nonce_match=$false;error=$null}
 try{
  Add-Type -AssemblyName System.Net.Http;[Net.ServicePointManager]::SecurityProtocol=$old -bor [Net.SecurityProtocolType]::Tls12
  $h=New-Object Net.Http.HttpClientHandler;$h.AllowAutoRedirect=$false;$h.UseCookies=$false
  $c=New-Object Net.Http.HttpClient($h);$c.Timeout=[TimeSpan]::FromSeconds(8)
  $response=Complete-DiagTask ($c.GetAsync(($Origin+'/probe/'+$Nonce),[Net.Http.HttpCompletionOption]::ResponseHeadersRead)) $clock;$r.http_status=[int]$response.StatusCode
  $stream=Complete-DiagTask ($response.Content.ReadAsStreamAsync()) $clock;$buffer=New-Object byte[] 16385;$count=0
  while($count -lt $buffer.Length){$n=Complete-DiagTask ($stream.ReadAsync($buffer,$count,$buffer.Length-$count)) $clock;if(!$n){break};$count+=$n}
  $bytes=if($count){$buffer[0..($count-1)]}else{@()};$cf=$response.Headers.Contains('CF-Ray') -or [string]$response.Headers.Server -match '(?i)cloudflare'
  $r=Classify-DiagHttp ([int]$response.StatusCode) $bytes $Nonce $cf;$r.error=$null
 }catch{if($null -ne $r.http_status){$r.outcome='HTTP_'+$r.http_status+'_BODY_ERROR'};$r.error=Get-DiagError $_.Exception}finally{$clock.Stop();$r.elapsed_ms=[int]$clock.ElapsedMilliseconds;if($stream){$stream.Dispose()};if($response){$response.Dispose()};if($c){$c.Dispose()};[Net.ServicePointManager]::SecurityProtocol=$old}
 return $r
}
function Get-DiagDnsTask([string]$HostName){return ,[Net.Dns]::GetHostAddressesAsync($HostName)}
function Resolve-DiagDns([string]$Origin) {
 $r=@{resolved=$false;ipv4=$false;ipv6=$false;error=$null};$clock=[Diagnostics.Stopwatch]::StartNew()
 try{$task=Get-DiagDnsTask ([Uri]$Origin).DnsSafeHost;if(!$task.Wait(6000)){throw (New-Object TimeoutException('DNS_DEADLINE'))};$addresses=$task.GetAwaiter().GetResult();$r.resolved=$addresses.Count -gt 0;$r.ipv4=@($addresses|Where-Object {$_.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork}).Count -gt 0;$r.ipv6=@($addresses|Where-Object {$_.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetworkV6}).Count -gt 0}catch{$r.error=Get-DiagError $_.Exception}
 $r.elapsed_ms=[int]$clock.ElapsedMilliseconds;return $r
}
function Wait-DiagTunnel($State,[bool]$RequireRegistration,[int]$Attempts=12,[int]$DelaySeconds=2,[string]$ExistingOrigin='') {
 $origin=$ExistingOrigin;$registered=$false;$errors=0;$i=0;$signals=[ordered]@{error=$false;dns=$false;timeout=$false;tls=$false;refused=$false;connect_failed=$false}
 $patterns=@{error='(?i)\bERR\b|\berror\b';dns='(?i)lookup|no such host|name resolution';timeout='(?i)timeout|timed out|deadline exceeded';tls='(?i)x509|certificate|TLS handshake';refused='(?i)connection refused';connect_failed='(?i)failed to connect|unable to establish|dial tcp'}
 for($i=1;$i -le $Attempts;$i++){
  $r=Invoke-ProbeDocker @('logs','--tail','100',$State.tunnel) 3
  if($r.exit_code -eq 0 -and !$r.timed_out){$logs=$r.stdout+"`n"+$r.stderr;$found=Get-ProbeUrl $logs;if($found){$origin=$found};$registered=$logs -cmatch 'Registered tunnel connection\b';foreach($key in $patterns.Keys){$signals[$key]=$signals[$key] -or ($logs -match $patterns[$key])}}else{$errors++}
  if($origin -and (!$RequireRegistration -or $registered)){break};if($i -lt $Attempts){Start-Sleep -Seconds $DelaySeconds}
 }
 return @{origin=$origin;url_issued=[bool]$origin;registered=$registered;log_reads=[Math]::Min($i,$Attempts);log_read_errors=$errors;log_signals=$signals}
}
function Get-DiagContainerState([string]$Name) {
 $r=Invoke-ProbeDocker @('inspect','--type','container','--format','{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}',$Name) 5
 if($r.exit_code -eq 0 -and !$r.timed_out -and $r.stdout -cmatch '^(created|running|paused|restarting|removing|exited|dead)\|([0-9]{1,5})\|(true|false)$'){return @{known=$true;state=$Matches[1];exit_code=[int]$Matches[2];oom=($Matches[3] -ceq 'true')}}
 return @{known=$false;state='unknown';exit_code=$null;oom=$null;command_timed_out=[bool]$r.timed_out}
}
function Test-DiagOrigin($State,[string]$HostName) {
 $code=@'
import json,os,socket,urllib.request
nonce=os.environ['FUCHENG_PROBE_NONCE'];host='HOST';opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));r={'http_status':None,'nonce_match':False,'dns_resolved':False,'error_type':None}
try:
 socket.getaddrinfo(host,8080);r['dns_resolved']=True
 with opener.open('http://'+host+':8080/probe/'+nonce,timeout=4) as response:
  r['http_status']=response.status;data=json.loads(response.read(1025));r['nonce_match']=isinstance(data,dict) and list(data)==['nonce'] and data['nonce']==nonce
except Exception as e:
 r['error_type']=type(e).__name__ if type(e).__name__ in ('URLError','HTTPError','TimeoutError','JSONDecodeError','OSError','gaierror') else 'OTHER'
 if isinstance(e,urllib.error.HTTPError):r['http_status']=e.code
print(json.dumps(r,separators=(',',':')))
'@
 $encoded=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($code.Replace('HOST',$HostName)))
 for($i=1;$i -le 3;$i++){
  $r=Invoke-ProbeDocker @('exec',$State.probe,'python','-c',("import base64;exec(base64.b64decode('"+$encoded+"'))")) 6
  if($r.exit_code -eq 0 -and !$r.timed_out -and $r.stdout.Length -le 1024){try{$v=$r.stdout|ConvertFrom-Json;if(@($v.PSObject.Properties).Count -eq 4 -and $v.http_status -in @($null,200,400,403,404,500,502,503,530) -and $v.nonce_match -is [bool] -and $v.dns_resolved -is [bool] -and $v.error_type -cin @($null,'URLError','HTTPError','TimeoutError','JSONDecodeError','OSError','gaierror','OTHER')){if($v.nonce_match -or $i -eq 3){return @{attempt=$i;http_status=$v.http_status;nonce_match=$v.nonce_match;dns_resolved=$v.dns_resolved;error_type=$v.error_type}}}}catch{}}
  if($i -lt 3){Start-Sleep -Seconds 1}
 }
 return @{attempt=3;http_status=$null;nonce_match=$false;dns_resolved=$false;error_type='EXEC_UNCONFIRMED'}
}
function Add-Diag([string]$Stage,$Value){
 $safe=$Value;if($Stage -cin @('url_issued','registration')){$safe=[ordered]@{};foreach($entry in $Value.GetEnumerator()){if($entry.Key -cne 'origin'){$safe[$entry.Key]=$entry.Value}}}
 $steps.Add([ordered]@{stage=$Stage;data=$safe});Write-Host ('- ['+$Stage+'] '+($safe|ConvertTo-Json -Depth 8 -Compress))
}
$steps=New-Object 'System.Collections.Generic.List[object]';$lock=$null;$watchdog=$null;$state=$null;$directory=$null;$docker=$null;$stage='workspace';$clean=$false
Write-Host '=== 府城 Tunnel 診斷開始 ==='
try{
 $local=[Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData);if(!$local -or ![IO.Path]::IsPathRooted($local)){throw 'LOCAL_DIRECTORY'}
 $root=Join-Path $local 'FuchengTunnelDiagnostic';Assert-NoToolLink $root;$marker=Join-Path $root 'owner.txt';Assert-NoToolLink $marker
 if(Test-Path -LiteralPath $root){if(!(Test-Path -LiteralPath $marker -PathType Leaf) -or [IO.File]::ReadAllText($marker) -cne 'fucheng-tunnel-diagnostic-v1'){throw 'OWNER'};if($env:OS -eq 'Windows_NT' -and (Get-Acl $root).GetOwner([Security.Principal.SecurityIdentifier]) -ne [Security.Principal.WindowsIdentity]::GetCurrent().User){throw 'OWNER'};foreach($item in @(Get-ChildItem $root -Recurse -Force)){Assert-NoToolLink $item.FullName}}else{[void][IO.Directory]::CreateDirectory($root);Set-ToolPrivateDirectory $root;[IO.File]::WriteAllText($marker,'fucheng-tunnel-diagnostic-v1',$utf8)}
 Set-ToolPrivateDirectory $root;$lock=[IO.File]::Open((Join-Path $root 'diagnostic.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
 $id=[Guid]::NewGuid().ToString('D');$prefix='fctd-'+$id.Replace('-','');$directory=Join-Path $root ('run-'+$id);[void][IO.Directory]::CreateDirectory($directory)
 $state=[ordered]@{run_id=$id;nonce=[Guid]::NewGuid().ToString('N');probe=($prefix+'-probe');tunnel=($prefix+'-tunnel');network=($prefix+'-net')};[IO.File]::WriteAllText((Join-Path $directory 'owned-resources.json'),($state|ConvertTo-Json),$utf8)
 $command=Get-Command 'docker.exe' -CommandType Application -ErrorAction SilentlyContinue|Select-Object -First 1;if(!$command){throw 'DOCKER_MISSING'};$docker=$command.Source
 $stage='images';foreach($image in @($appImage,$tunnelImage)){$r=Invoke-ProbeDocker @('image','inspect','--format','{{.Os}}|{{.Architecture}}',$image) 8;if($r.exit_code -ne 0 -or $r.stdout -cne 'linux|amd64'){throw 'PINNED_IMAGE_MISSING'}};Add-Diag 'images' @{available=$true;platform='linux/amd64';automatic_pull=$false}
 $watchdog=Start-ProbeWatchdog $state $directory;$stage='create';$labels=@('--label',('io.fucheng.feasibility.run='+$id),'--label','io.fucheng.feasibility.kind=nonce-only-v1')
 $r=Invoke-ProbeDocker (@('network','create','--driver','bridge')+$labels+@($state.network)) 10;if($r.exit_code -ne 0 -or $r.timed_out){throw 'NETWORK_CREATE'}
 $encoded=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((Get-NonceServerSource)));$python="import base64;exec(base64.b64decode('$encoded'))"
 $shared=@('--detach','--platform','linux/amd64','--network',$state.network,'--restart','no','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','32','--memory','128m','--cpus','0.5')+$labels
 $r=Invoke-ProbeDocker (@('run','--name',$state.probe)+$shared+@('--network-alias','nonce-probe','--user','10001','--env',('FUCHENG_PROBE_NONCE='+$state.nonce),'--entrypoint','python',$appImage,'-u','-c',$python)) 15;if($r.exit_code -ne 0 -or $r.timed_out){throw 'NONCE_CREATE'}
 $stage='origin';Add-Diag 'local_origin' (Test-DiagOrigin $state '127.0.0.1');Add-Diag 'bridge_alias_origin' (Test-DiagOrigin $state 'nonce-probe')
 $r=Invoke-ProbeDocker (@('run','--name',$state.tunnel)+$shared+@($tunnelImage,'tunnel','--no-autoupdate','--protocol','http2','--url','http://nonce-probe:8080')) 15;if($r.exit_code -ne 0 -or $r.timed_out){throw 'TUNNEL_CREATE'}
 $stage='tunnel_url';$early=Wait-DiagTunnel $state $false;Add-Diag 'url_issued' $early
 if($early.origin){$stage='early_https';Add-Diag 'windows_dns' (Resolve-DiagDns $early.origin);Add-Diag 'early_https' @{registered_when_url_seen=$early.registered;sample=(Invoke-DiagHttps $early.origin $state.nonce)}}
 $stage='registration';$ready=Wait-DiagTunnel $state $true 12 2 $early.origin;Add-Diag 'registration' $ready
 $samples=@();if($ready.origin){for($i=1;$i -le 6;$i++){$stage='later_https';$sample=Invoke-DiagHttps $ready.origin $state.nonce;$samples+=$sample;Add-Diag ('later_https_'+$i) $sample;if($i -lt 6){Start-Sleep -Seconds 3}}}else{Add-Diag 'later_https' @{skipped=$true;reason='NO_URL'}}
 Add-Diag 'nonce_container' (Get-DiagContainerState $state.probe);Add-Diag 'tunnel_container' (Get-DiagContainerState $state.tunnel)
 if($samples.Count -and !@($samples|Where-Object {$_.nonce_match}).Count){
  $curl=Get-Command 'curl.exe' -CommandType Application -ErrorAction SilentlyContinue|Select-Object -First 1
  if($curl){$saved=$docker;$docker=$curl.Source;try{$r=Invoke-ProbeDocker @('--silent','--show-error','--connect-timeout','4','--max-time','8','--output','NUL','--write-out','%{http_code}|%{time_total}|%{ssl_verify_result}',($ready.origin+'/probe/'+$state.nonce)) 9;$safe=@{exit_code=$r.exit_code;timed_out=$r.timed_out;transport_only=$true};if($r.stdout -cmatch '^([0-9]{3})\|([0-9.]{1,12})\|([0-9]{1,8})$'){$safe.http_status=[int]$Matches[1];$safe.seconds=$Matches[2];$safe.tls_verify_code=[int]$Matches[3]};Add-Diag 'curl_comparison' $safe}finally{$docker=$saved}}
 }
 $success=@($samples|Where-Object {$_.nonce_match}).Count;Add-Diag 'summary' @{after_registration_confirmed=$ready.registered;later_nonce_matches=$success;later_attempts=$samples.Count;original_failure_root_cause='UNPROVEN'}
 Write-Host '判讀：local_origin／bridge_alias_origin 判斷 origin；url_issued 不等於 registration；early 與 later 分開比較。HTTP 502／530 與 cf_error_code、DNS/TLS/timeout 分類供核對。本次成功也不證明前次就是啟動競態。'
}catch{$code=if($_.Exception.Message -cin @('LOCAL_DIRECTORY','OWNER','DOCKER_MISSING','PINNED_IMAGE_MISSING','NETWORK_CREATE','NONCE_CREATE','TUNNEL_CREATE','ORIGIN_INVALID')){$_.Exception.Message}else{'UNCLASSIFIED'};Add-Diag 'stopped' @{stage=$stage;code=$code;error=(Get-DiagError $_.Exception)}}finally{
 if($state -and $docker){$clean=Remove-ProbeResources $state};if($watchdog){if($clean -and !$watchdog.HasExited){$watchdog.Kill()};$watchdog.Dispose()};Add-Diag 'cleanup' @{confirmed=$clean;watchdog_started=($null -ne $watchdog);watchdog_seconds=480;nonce_self_exit_seconds=420;only_matching_run_labels=$true}
 if($directory){try{$json=[ordered]@{kind='tunnel_diagnostic';vantage='club-host-via-public-edge';checked_at=(Get-Date).ToUniversalTime().ToString('o');steps=$steps.ToArray()};[IO.File]::WriteAllText((Join-Path $directory 'diagnostic.json'),($json|ConvertTo-Json -Depth 12),$utf8);$lines=@('# 府城 Tunnel 針對性診斷','原始失敗根因尚未證實；沒有重新做44項檢查、登入、上傳或操作舊報告。');foreach($item in $steps){$lines+=('- ['+$item.stage+'] '+($item.data|ConvertTo-Json -Depth 8 -Compress))};[IO.File]::WriteAllText((Join-Path $directory 'diagnostic.md'),($lines -join "`r`n"),(New-Object Text.UTF8Encoding($true)));Write-Host ('本次安全診斷結果位置：'+$directory)}catch{Write-Host ('結果保存未確認；type='+$_.Exception.GetType().FullName)}}
 if($lock){$lock.Dispose()};Write-Host '=== 府城 Tunnel 診斷結束 ==='
}
}
