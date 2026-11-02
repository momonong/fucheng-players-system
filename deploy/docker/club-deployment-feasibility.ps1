& {
# Paste this entire block into Windows PowerShell 5.1. No permanent execution-policy change.
$ErrorActionPreference='Stop';$utf8=New-Object Text.UTF8Encoding($false)
$endpoint='https://momonong.me/fucheng/api/deployment-reports';$deviceId='club-windows-01'
$appImage='momonong/fucheng-players-system@sha256:0e5a297b0d16876fa56e1b9bed0470c3b8632d55ded6b23ffc5c18315f39e6e2'
$tunnelImage='cloudflare/cloudflared@sha256:faa8e0a1475f137c910be6025f43c8e4092fdd35461b31e19fd1390657a1ff39'
$bootstrapHash='f54a5e9d21e6ef7affdb172823ebd3ff9d6f6783223227f184b99c39c3b1764f'
$zipHash='3db404e85a53492a0eea347cc3f5409f5f238395d88eca12feb2aba0c5005956'
$toolBase='https://momonong.me/fucheng/api/deployment-tools/'
function Hash-ProbeBytes([byte[]]$Bytes) {
 $h=[Security.Cryptography.SHA256]::Create();try{([BitConverter]::ToString($h.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()}
}
function Get-InitialTool([string]$Url) {
 Add-Type -AssemblyName System.Net.Http
 $old=[Net.ServicePointManager]::SecurityProtocol;$c=$null;$r=$null
 try {
  [Net.ServicePointManager]::SecurityProtocol=$old -bor [Net.SecurityProtocolType]::Tls12
  $h=New-Object Net.Http.HttpClientHandler;$h.AllowAutoRedirect=$false
  $c=New-Object Net.Http.HttpClient($h);$c.Timeout=[TimeSpan]::FromSeconds(30);$c.MaxResponseContentBufferSize=2097152
  $r=$c.GetAsync($Url).GetAwaiter().GetResult();if([int]$r.StatusCode -ne 200){throw 'DOWNLOAD_REFUSED'}
  return ,$r.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
 } finally {if($r){$r.Dispose()};if($c){$c.Dispose()};[Net.ServicePointManager]::SecurityProtocol=$old}
}
function Import-ProbeFunctions([string]$Source,[string[]]$Names) {
 $t=$null;$e=$null;$a=[Management.Automation.Language.Parser]::ParseInput($Source,[ref]$t,[ref]$e)
 if($e.Count){throw 'TOOL_PARSE'}
 foreach($name in $Names){
  $f=@($a.EndBlock.Statements|Where-Object {$_ -is [Management.Automation.Language.FunctionDefinitionAst] -and $_.Name -ceq $name})
  if($f.Count -ne 1){throw 'TOOL_FUNCTION'}
  # Explicitly install only allowlisted, body-hash-verified top-level definitions.
  $parameters=if($f[0].Parameters.Count){'param('+(@($f[0].Parameters|ForEach-Object {$_.Extent.Text}) -join ',')+")`n"}else{''}
  Set-Item -Path ('function:script:'+$name) -Value ([scriptblock]::Create($parameters+$f[0].Body.Extent.Text.Substring(1,$f[0].Body.Extent.Text.Length-2)))
 }
}
function Write-ProbeJson([string]$Path,$Value) {
 $b=$utf8.GetBytes(($Value|ConvertTo-Json -Depth 12)+"`n")
 $f=[IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
 try{$f.Write($b,0,$b.Length);$f.Flush($true)}finally{$f.Dispose()}
}
function Read-ProbeJson([string]$Path,[int]$Max=262144) {
 Assert-NoToolLink $Path;$f=Get-Item -LiteralPath $Path
 if($f.PSIsContainer -or $f.Length -lt 2 -or $f.Length -gt $Max){throw 'LOCAL_FILE_INVALID'}
 return [IO.File]::ReadAllText($Path,$utf8)|ConvertFrom-Json
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
 foreach($name in @('Stop-OwnedProcessTree','Invoke-Bounded','Quote-ProbeArgument','Invoke-ProbeDocker','Remove-ProbeResources')){$source+="`nfunction $name {"+(Get-Command $name).Definition+"}`n"}
 $source+="Start-Sleep -Seconds 600;`$null=Remove-ProbeResources `$s"
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
threading.Timer(240,lambda:os._exit(0)).start()
http.server.HTTPServer(('0.0.0.0',8080),Handler).serve_forever()
'@
}
function Get-ProbeUrl([string]$Logs) {
 $matches=[regex]::Matches($Logs,'(?<![A-Za-z0-9./-])https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com(?=[\s|]|$)')
 if($matches.Count){return $matches[0].Value};return $null
}
function Measure-ProbeHttps([string]$Origin,[string]$Nonce,[int]$Attempts=5) {
 if($Origin -cnotmatch '^https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com$'){throw 'PROBE_ORIGIN'}
 $times=@();$success=0
 for($i=0;$i -lt $Attempts;$i++){
  $clock=[Diagnostics.Stopwatch]::StartNew()
  try{
   $b=Invoke-ToolHttp ($Origin+'/probe/'+$Nonce) 'GET' @() $null '' 1024 8
   $v=[Text.Encoding]::UTF8.GetString($b)|ConvertFrom-Json
   if(@($v.PSObject.Properties).Count -eq 1 -and $v.nonce -ceq $Nonce){$success++;$times+=([int]$clock.ElapsedMilliseconds)}
  }catch{}finally{$clock.Stop()}
 }
 $sorted=@($times|Sort-Object)
 return @{attempts=$Attempts;successes=$success;minimum_ms=if($success){$sorted[0]}else{$null};median_ms=if($success){$sorted[[int][Math]::Floor(($success-1)/2)]}else{$null};maximum_ms=if($success){$sorted[-1]}else{$null}}
}
function Set-FeasibilityCheck([hashtable]$Checks,[string]$Id,[string]$Status,[string]$Reason,[string]$Evidence,[string]$Next) {
 $Checks[$Id]=[ordered]@{id=$Id;status=$Status;reason=$Reason;evidence=$Evidence;next_action=$Next}
}
function Invoke-FeasibilityProbe($State,[string]$Directory) {
 $checks=@{};$executed=$false;$public=$false;$watchdog=$null;$clean=$false
 foreach($id in @('probe_image','isolated_probe','quick_tunnel','public_https_nonce','https_samples')){Set-FeasibilityCheck $checks $id 'NOT_TESTED' 'Temporary nonce probe has not completed.' 'No positive result recorded.' 'Inspect this report before formal installation.'}
 try {
  if(!$docker){throw 'DOCKER_UNAVAILABLE'}
  if(!(Remove-ProbeResources $State)){throw 'PRIOR_CLEANUP_UNCONFIRMED'}
  $watchdog=Start-ProbeWatchdog $State $Directory
  foreach($image in @($appImage,$tunnelImage)){
   Write-Host '核對／下載固定 digest 的 Linux amd64 測試 image（每個最多 90 秒）。'
   $r=Invoke-ProbeDocker @('image','inspect','--format','{{.Os}}|{{.Architecture}}',$image) 8
   if($r.exit_code -ne 0){$r=Invoke-ProbeDocker @('pull','--platform','linux/amd64',$image) 90;if($r.exit_code -ne 0 -or $r.timed_out){throw 'IMAGE_PULL_FAILED'};$r=Invoke-ProbeDocker @('image','inspect','--format','{{.Os}}|{{.Architecture}}',$image) 8}
   if($r.exit_code -ne 0 -or $r.stdout -cne 'linux|amd64'){throw 'IMAGE_PLATFORM'}
  }
  Set-FeasibilityCheck $checks 'probe_image' 'PASS' 'Both digest-pinned Linux amd64 images are available.' 'app=1.2.0 pinned digest; cloudflared=2026.10.3 pinned manifest digest.' 'Formal deployment must retain reviewed digests.'
  $labels=@('--label',('io.fucheng.feasibility.run='+$State.run_id),'--label','io.fucheng.feasibility.kind=nonce-only-v1')
  $r=Invoke-ProbeDocker (@('network','create','--driver','bridge')+$labels+@($State.network)) 10
  if($r.exit_code -ne 0 -or $r.timed_out){throw 'NETWORK_CREATE'}
  $python=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((Get-NonceServerSource)))
  $command="import base64;exec(base64.b64decode('$python'))"
  $r=Invoke-ProbeDocker (@('run','--detach','--name',$State.probe,'--platform','linux/amd64','--network',$State.network,'--network-alias','nonce-probe','--restart','no','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','32','--memory','96m','--cpus','0.5','--user','10001','--env',('FUCHENG_PROBE_NONCE='+$State.nonce),'--entrypoint','python')+$labels+@($appImage,'-u','-c',$command)) 15
  if($r.exit_code -ne 0 -or $r.timed_out){throw 'PROBE_CREATE'};$executed=$true
  Set-FeasibilityCheck $checks 'isolated_probe' 'PASS' 'Nonce-only Python HTTP process started in an isolated bridge.' 'No volumes, host networking, LAN port publishing, admin interface, or membership data; self-exit=240s.' 'This synthetic server does not validate app data migration or backup restore.'
  $r=Invoke-ProbeDocker (@('run','--detach','--name',$State.tunnel,'--platform','linux/amd64','--network',$State.network,'--restart','no','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','32','--memory','128m','--cpus','0.5')+$labels+@($tunnelImage,'tunnel','--no-autoupdate','--protocol','http2','--url','http://nonce-probe:8080')) 15
  if($r.exit_code -ne 0 -or $r.timed_out){throw 'TUNNEL_CREATE'}
  $origin=$null;$clock=[Diagnostics.Stopwatch]::StartNew()
  while($clock.Elapsed.TotalSeconds -lt 40){
   $log=Invoke-ProbeDocker @('logs','--tail','80',$State.tunnel) 3
   # Logs stay in memory; only the strict Quick Tunnel origin can enter further requests.
   $origin=Get-ProbeUrl ($log.stdout+"`n"+$log.stderr)
   if($origin){break};Start-Sleep -Milliseconds 1000
  }
  if(!$origin){throw 'TUNNEL_URL_TIMEOUT'};$public=$true
  Set-FeasibilityCheck $checks 'quick_tunnel' 'PASS' 'A temporary Quick Tunnel URL was issued; HTTP/2 was explicitly selected.' 'protocol=http2; ephemeral trycloudflare hostname; QUIC was not tested.' 'Permanent tunnel, owned domain and policy configuration remain separate.'
  Write-Host '以真正公開 HTTPS 回讀隨機 nonce；最多五次，每次 8 秒，不接受重新導向。'
  $sample=Measure-ProbeHttps $origin $State.nonce 5
  $status=if($sample.successes -eq 5){'PASS'}elseif($sample.successes -gt 0){'WARN'}else{'FAIL'}
  Set-FeasibilityCheck $checks 'public_https_nonce' $(if($sample.successes){'PASS'}else{'FAIL'}) 'TLS-validated HTTPS response must contain the exact nonce and no other fields.' ('vantage=club-host-via-public-edge; nonce_matches='+$sample.successes+'/5; redirects=refused.') 'Verify separately from a phone on another network; this is not that acceptance.'
  Set-FeasibilityCheck $checks 'https_samples' $status 'Five bounded HTTPS samples measure only this short test interval.' ('successes={0}/5; min_ms={1}; median_ms={2}; max_ms={3}; protocol=http2.' -f $sample.successes,$sample.minimum_ms,$sample.median_ms,$sample.maximum_ms) 'Transient results do not establish long-term uptime or performance.'
 }catch{
  foreach($id in @('probe_image','isolated_probe','quick_tunnel','public_https_nonce','https_samples')){if($checks[$id].status -ceq 'NOT_TESTED'){Set-FeasibilityCheck $checks $id 'FAIL' 'The bounded temporary probe stopped before this step completed.' 'Raw Docker output, exception message and network bodies are intentionally omitted.' 'Review host Docker and outbound connectivity; rerun only after retaining this report.';break}}
 }finally{
  if($docker){
   if(!$executed){$started=Invoke-ProbeDocker @('inspect','--type','container','--format','{{.State.StartedAt}}|{{index .Config.Labels "io.fucheng.feasibility.run"}}',$State.probe) 5;if($started.exit_code -eq 0 -and $started.stdout -cmatch ('^(?!0001)[^|]+\|'+[regex]::Escape($State.run_id)+'$')){$executed=$true}}
   $clean=Remove-ProbeResources $State
  }else{$clean=$false}
  if($watchdog){if($clean -and !$watchdog.HasExited){$watchdog.Kill()};$watchdog.Dispose()}
  Set-FeasibilityCheck $checks 'temporary_cleanup' $(if($clean){'PASS'}else{'WARN'}) 'Only exact resource IDs with matching run and nonce-only labels are eligible for removal.' $(if($clean){'Both temporary containers and their bridge were removed or confirmed absent; no volumes were used.'}elseif($watchdog){'Cleanup not confirmed; the independent watchdog will retry after 600s; preserve this workspace.'}else{'Cleanup not confirmed; Docker or the watchdog was unavailable; preserve this workspace.'}) 'Never use Docker prune or remove existing volumes; inspect only this run if cleanup remains unknown.'
 }
 return @{checks=$checks;container_execution=$executed;temporary_public_probe=$public;cleanup=$clean}
}
function Patch-ConsoleCredential([string]$Path) {
 $b=[IO.File]::ReadAllBytes($Path)
 if((Hash-ProbeBytes $b) -cne 'df6d8364595138e935e8baa8975b302426b846a2cd87ce6010b14e32ed6dd669'){throw 'CREDENTIAL_HASH'}
 $s=[Text.Encoding]::UTF8.GetString($b).TrimStart([char]0xFEFF)
 $old=@("    `$credential = Get-Credential -Message 'momonong.me/fucheng 接收站管理員（密碼不會顯示或寫入檔案）'","    if (!`$credential) { throw 'cancelled' }") -join "`n"
 $new=@("    `$consoleStage='prompt'","    `$username=Read-Host -Prompt 'momonong.me/fucheng 接收站管理員帳號'","    if([string]::IsNullOrWhiteSpace(`$username)){throw 'EMPTY_USERNAME'}","    `$secure=Read-Host -AsSecureString -Prompt '管理員密碼（隱藏輸入）'","    if(!`$secure -or !`$secure.Length){throw 'EMPTY_PASSWORD'}","    `$credential=New-Object Management.Automation.PSCredential(`$username.Trim(),`$secure)") -join "`n"
 $edits=[ordered]@{};$edits[$old]=$new
 $edits['    $login = $utf8.GetString']="    `$consoleStage='login'`n    `$login = `$utf8.GetString"
 $edits['    $value = $utf8.GetString']="    `$consoleStage='capability'`n    `$value = `$utf8.GetString"
 $edits['    $tokenPath = Join-Path']="    `$consoleStage='token_write'`n    `$tokenPath = Join-Path"
 $edits["    Write-Host '接收站登入或取得回傳權限失敗。請核對既有管理員；不要傳送密碼、session 或 token。'"]="    `$safeStage=if(`$consoleStage -cin @('prompt','login','capability','token_write')){`$consoleStage}else{'prepare'}`n    Write-Host ('回傳準備失敗：stage={0}; type={1}。不要貼出密碼或 token。' -f `$safeStage,`$_.Exception.GetType().FullName)"
 foreach($p in $edits.GetEnumerator()){if(([regex]::Matches($s,[regex]::Escape($p.Key))).Count -ne 1){throw 'CONSOLE_PATCH'};$s=$s.Replace($p.Key,$p.Value)}
 $copy=Join-Path ([IO.Path]::GetDirectoryName($Path)) 'console-credential.ps1';[IO.File]::WriteAllText($copy,$s,(New-Object Text.UTF8Encoding($true)));return $copy
}
function Get-HostAwareHealth {
 # Inspect only the public origin key, never full environment or mounts.
 $template='{{range .Config.Env}}{{if eq (index (split . "=") 0) "FUCHENG_PUBLIC_ORIGIN"}}{{.}}{{end}}{{end}}'
 $r=Invoke-ProbeDocker @('inspect','--type','container','--format',$template,'fucheng-check-v120') 5
 $origin=$null
 if($r.exit_code -ne 0 -or $r.timed_out -or $r.stdout.Length -gt 320 -or $r.stdout -cnotmatch '^FUCHENG_PUBLIC_ORIGIN=(https?://[^/\s]+)$'){return $null}
 if(![Uri]::TryCreate($Matches[1],[UriKind]::Absolute,[ref]$origin) -or $origin.UserInfo -or $origin.Query -or $origin.Fragment -or $origin.Authority -cnotmatch '^[A-Za-z0-9.:[\]-]+$'){return $null}
 $hostHeader=$origin.Authority
 $r=Invoke-ProbeDocker @('inspect','--type','container','--format','{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.HostConfig.RestartPolicy.Name}}|{{.RestartCount}}','fucheng-check-v120') 5
 if($r.exit_code -ne 0 -or $r.timed_out -or $r.stdout -cnotmatch '^(running|exited|created|paused|restarting|dead|removing)\|(healthy|unhealthy|starting|none)\|(no|always|unless-stopped|on-failure|)\|([0-9]+)$'){return $null}
 $state=$Matches[1];$health=$Matches[2];$restart=$Matches[3]
 $curl=Get-Command 'curl.exe' -CommandType Application -ErrorAction SilentlyContinue|Select-Object -First 1
 if(!$curl){return $null}
 $arguments='--silent --show-error --noproxy "*" --max-time 5 --output NUL --write-out "%{http_code}" --header '+(Quote-ProbeArgument ('Host: '+$hostHeader))+' "http://127.0.0.1:8052/api/health"'
 $answer=Invoke-Bounded $curl.Source $arguments 6
 $status=if($answer.exit_code -eq 0 -and !$answer.timed_out -and $answer.stdout -cmatch '^[0-9]{3}$'){$answer.stdout}else{'not_tested'}
 $checks=@{};Set-FeasibilityCheck $checks 'project_health' $(if($state -ceq 'running' -and $health -ceq 'healthy' -and $restart -cin @('always','unless-stopped') -and $status -ceq '200'){'PASS'}else{'WARN'}) 'Specified trial container and loopback health were read with its configured public Host header.' ('container=fucheng-check-v120; state='+$state+'; health='+$health+'; restart='+$restart+'; local_http='+$status+'; host_header=configured_public_origin.') 'This is local health only; it does not prove reboot recovery or public app acceptance.'
 return $checks.project_health
}
function New-FeasibilityReport($HostReport,$Probe) {
 $checks=@{};foreach($c in $HostReport.checks){$checks[[string]$c.id]=$c}
 foreach($key in $Probe.checks.Keys){$checks[$key]=$Probe.checks[$key]}
 Set-FeasibilityCheck $checks 'public_ip_observation' 'NOT_TESTED' 'Public address family has not been observed.' 'No full public IP address is recorded.' 'One observed address never proves static addressing or CGNAT.'
 try{
  $trace=[Text.Encoding]::UTF8.GetString((Invoke-ToolHttp 'https://www.cloudflare.com/cdn-cgi/trace' 'GET' @() $null '' 8192 6))
  $ipLine=@($trace -split "`n"|Where-Object {$_ -cmatch '^ip='})
  $ip=$null
  if($ipLine.Count -eq 1 -and [Net.IPAddress]::TryParse($ipLine[0].Substring(3).Trim(),[ref]$ip)){
   $family=if($ip.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork){'IPv4'}else{'IPv6'}
   Set-FeasibilityCheck $checks 'public_ip_observation' 'PASS' 'Cloudflare official HTTPS trace returned a public egress address family.' ('observed_family='+$family+'; full_ip=not_stored; other_family=not_tested.') 'This single observation does not prove static addressing, inbound reachability or CGNAT.'
  }
 }catch{}
 Set-FeasibilityCheck $checks 'static_ip_contract' 'NOT_TESTED' 'No ISP contract was inspected.' 'Static IP cannot be established by a one-time network probe.' 'Ask the ISP or inspect the service contract before relying on a fixed WAN IP.'
 Set-FeasibilityCheck $checks 'isp_inbound_policy' 'NOT_TESTED' 'WAN routing, ISP inbound policy and router control were not inspected.' 'Only a temporary outbound Tunnel was tested; no inbound ports or firewall rules were changed.' 'Direct ingress needs separate ISP/router and independent external checks.'
 foreach($id in @('domain_dns','domain_control')){Set-FeasibilityCheck $checks $id 'NOT_TESTED' 'The club-owned domain has not been supplied to this test.' 'Domain availability and ownership remain unknown.' 'Use the club-owned domain when preparing permanent ingress.'}
 Set-FeasibilityCheck $checks 'public_ingress' 'NOT_TESTED' 'Independent external-device acceptance was not performed.' 'The nonce probe originates on this host via the public edge; it is not a phone on another network.' 'From another network validate the future owned-domain app URL.'
 $counts=[ordered]@{PASS=0;WARN=0;FAIL=0;NOT_TESTED=0};foreach($c in $checks.Values){$counts[$c.status]++}
 if($checks.Count -ne 44){throw 'REPORT_CHECK_COUNT'}
 return [ordered]@{schema_version=3;report_type='deployment_feasibility';checked_at=(Get-Date).ToUniversalTime().ToString('o');host=$HostReport.host;
  scope=[ordered]@{read_only_probes=$false;container_execution=[bool]$Probe.container_execution;host_control=$false;live_volume_access=$false;temporary_public_probe=[bool]$Probe.temporary_public_probe;external_network_opt_in=$true};
  summary=$counts;checks=@($checks.Values|Sort-Object id);recommendations=@(
   [ordered]@{candidate='Cloudflare Tunnel 可行性';status=$checks.public_https_nonce.status;reason='以無資料 nonce-only 容器經 HTTP/2 暫時 Tunnel 做真正 HTTPS 回讀；成功僅支持本次主機出口與短暫回連可行。';next_action='正式入口仍需球館網域、持久 Tunnel、管理權限與另一網路手機驗收。'},
   [ordered]@{candidate='正式服務維運驗收';status='NOT_TESTED';reason='本次未操作正式 volume、備份還原、migration、開機、電源、防火牆或服務設定。';next_action='依獨立授權完成真實備份還原與受控重啟；本工具不執行。'},
   [ordered]@{candidate='直接入站 TLS';status='NOT_TESTED';reason='ISP 合約、WAN 入站與網域未確認；不能由私有 LAN IP 推論 CGNAT。';next_action='若考慮直連，另核對 ISP、路由器、80/443 與憑證續期。'});
  sources=@('https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/','https://docs.docker.com/engine/network/drivers/bridge/','https://docs.docker.com/desktop/setup/install/windows-install/')}
}
$lock=$null;$tokenFile=$null;$stage='download';$directory=$null
try {
 Write-Host '部署可行性測試：只建立暫時 nonce 容器／公開 Tunnel，結束即清理；不碰正式資料，不重開機。'
 $b=Get-InitialTool ($toolBase+$bootstrapHash+'/bootstrap.ps1')
 if((Hash-ProbeBytes $b) -cne $bootstrapHash){throw 'BOOTSTRAP_HASH'}
 Import-ProbeFunctions ([Text.Encoding]::UTF8.GetString($b).TrimStart([char]0xFEFF)) @('Invoke-ToolHttp','Assert-NoToolLink','Set-ToolPrivateDirectory','Expand-VerifiedToolZip','Invoke-BootstrapChild')
 $stage='workspace';$local=[Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
 if(!$local -or ![IO.Path]::IsPathRooted($local)){throw 'LOCAL_DIRECTORY'}
 $downloadRoot=Join-Path $local 'FuchengDeploymentCheck';Assert-NoToolLink $downloadRoot
 $marker=Join-Path $downloadRoot 'owner.txt';Assert-NoToolLink $marker
 if(Test-Path -LiteralPath $downloadRoot){
  if(!(Test-Path -LiteralPath $marker -PathType Leaf) -or [IO.File]::ReadAllText($marker) -cne 'fucheng-deployment-feasibility-v1'){throw 'WORKSPACE_OWNER'}
  if($env:OS -eq 'Windows_NT' -and (Get-Acl $downloadRoot).GetOwner([Security.Principal.SecurityIdentifier]) -ne [Security.Principal.WindowsIdentity]::GetCurrent().User){throw 'WORKSPACE_ACCOUNT'}
  foreach($item in @(Get-ChildItem -LiteralPath $downloadRoot -Recurse -Force)){Assert-NoToolLink $item.FullName}
 }else{[void][IO.Directory]::CreateDirectory($downloadRoot);Set-ToolPrivateDirectory $downloadRoot;[IO.File]::WriteAllText($marker,'fucheng-deployment-feasibility-v1',$utf8)}
 Set-ToolPrivateDirectory $downloadRoot
 $lock=[IO.File]::Open((Join-Path $downloadRoot 'check.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
 $stage='tools';$zip=Invoke-ToolHttp ($toolBase+$zipHash+'/tools.zip')
 if((Hash-ProbeBytes $zip) -cne $zipHash){throw 'ZIP_HASH'}
 $run=Join-Path $downloadRoot ('kit-'+[Guid]::NewGuid().ToString('N'));[void][IO.Directory]::CreateDirectory($run)
 $archive=Join-Path $run 'tools.zip';[IO.File]::WriteAllBytes($archive,$zip);$kit=Join-Path $run 'kit';Expand-VerifiedToolZip $archive $kit
 $native=Join-Path $kit 'deploy/docker/host-preflight.ps1'
 Import-ProbeFunctions ([IO.File]::ReadAllText($native).TrimStart([char]0xFEFF)) @('Stop-OwnedProcessTree','Invoke-Bounded')
 $d=Get-Command 'docker.exe' -CommandType Application -ErrorAction SilentlyContinue|Select-Object -First 1
 $docker=if($d){$d.Source}else{$null}
 $activePath=Join-Path $downloadRoot 'active-check.json'
 if(Test-Path -LiteralPath $activePath){
  $state=Read-ProbeJson $activePath 8192
  if($state.schema_version -ne 1 -or [string]$state.run_id -cnotmatch '^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$' -or $state.nonce -cnotmatch '^[0-9a-f]{32}$' -or $state.directory -cne ('data/check-'+$state.run_id.Replace('-',''))){throw 'ACTIVE_INVALID'}
  $prefix='fcp-'+$state.run_id.Replace('-','');if($state.probe -cne ($prefix+'-probe') -or $state.tunnel -cne ($prefix+'-tunnel') -or $state.network -cne ($prefix+'-net')){throw 'RESOURCE_BINDING'}
 }else{
  $priorData=Join-Path $downloadRoot 'data'
  if((Test-Path -LiteralPath $priorData) -and @(Get-ChildItem -LiteralPath $priorData -Force).Count){throw 'ACTIVE_MISSING_WITH_PRIOR_DATA'}
  $id=[Guid]::NewGuid().ToString('D');$short=$id.Replace('-','');$prefix='fcp-'+$short
  $state=[ordered]@{schema_version=1;run_id=$id;nonce=[Guid]::NewGuid().ToString('N');directory=('data/check-'+$short);probe=($prefix+'-probe');tunnel=($prefix+'-tunnel');network=($prefix+'-net')}
  Write-ProbeJson $activePath $state
 }
 $directory=Join-Path $downloadRoot $state.directory;[void][IO.Directory]::CreateDirectory($directory)
 $reportPath=Join-Path $directory 'report.json'
 if(!(Test-Path -LiteralPath $reportPath) -and ((Test-Path -LiteralPath (Join-Path $directory 'upload-operation.json')) -or (Test-Path -LiteralPath (Join-Path $directory 'report.md')))){throw 'ORIGINAL_PAYLOAD_MISSING'}
 if(!(Test-Path -LiteralPath $reportPath)){
  $stage='host_preflight';$hostPath=Join-Path $directory 'host-report.json'
  if(!(Test-Path -LiteralPath $hostPath)){
   $hostDir=Join-Path $kit 'data/host-readonly'
   $result=Invoke-BootstrapChild $native @{OutputDir=$hostDir;InstallPath=$downloadRoot;ContainerName='fucheng-check-v120';TestPort=8052;ImageRef=$appImage;TimeoutSeconds=5;ProbeNetwork=$true} 240
   if(!(Test-Path -LiteralPath (Join-Path $hostDir 'report.json'))){throw 'HOST_REPORT_MISSING'}
   [IO.File]::Copy((Join-Path $hostDir 'report.md'),(Join-Path $directory 'host-report.md'),$false);[IO.File]::Copy((Join-Path $hostDir 'report.json'),$hostPath,$false)
  }
  $hostReport=Read-ProbeJson $hostPath
  $stage='temporary_probe';$probe=Invoke-FeasibilityProbe $state $directory
  $correctedHealth=$null;try{$correctedHealth=Get-HostAwareHealth}catch{}
  if($correctedHealth){$probe.checks['project_health']=$correctedHealth}
  $report=New-FeasibilityReport $hostReport $probe
  $lines=@('# 球館部署可行性實測','','此報告執行暫時 nonce-only 容器與 Tunnel；無正式資料、無主機設定變更。','vantage=club-host-via-public-edge；不是獨立手機驗收。','')
  foreach($c in $report.checks){$lines+=('- '+$c.id+' ['+$c.status+'] '+$c.evidence)}
  if(!(Test-Path -LiteralPath (Join-Path $directory 'report.md'))){[IO.File]::WriteAllText((Join-Path $directory 'report.md'),($lines -join "`r`n"),(New-Object Text.UTF8Encoding($true)))}
  Write-ProbeJson $reportPath $report
  Write-Host ('部署可行性報告：PASS={0} WARN={1} FAIL={2} NOT_TESTED={3}；原主機健檢另存 host-report.json。' -f $report.summary.PASS,$report.summary.WARN,$report.summary.FAIL,$report.summary.NOT_TESTED)
 }
 $stage='upload_prepare';$body=[IO.File]::ReadAllBytes($reportPath);$r=Read-ProbeJson $reportPath
 if($r.schema_version -ne 3 -or $r.report_type -cne 'deployment_feasibility'){throw 'REPORT_SCHEMA'}
 $operationPath=Join-Path $directory 'upload-operation.json'
 if(!(Test-Path -LiteralPath $operationPath)){Write-ProbeJson $operationPath ([ordered]@{schema_version=1;report_id=$state.run_id;endpoint=$endpoint;device_id=$deviceId;raw_report_sha256=(Hash-ProbeBytes $body)})}
 $op=Read-ProbeJson $operationPath 8192
 if($op.report_id -cne $state.run_id -or $op.raw_report_sha256 -cne (Hash-ProbeBytes $body) -or $op.endpoint -cne $endpoint -or $op.device_id -cne $deviceId){throw 'OPERATION_BINDING'}
 $config=Join-Path $kit 'private/club-report.json';Write-ProbeJson $config ([ordered]@{endpoint=$endpoint;device_id=$deviceId;token_file='report-upload-token.txt'})
 $sender=Join-Path $kit 'deploy/docker/send-host-report.ps1';$source=[IO.File]::ReadAllText($sender)
 $old="    if (`$report.schema_version -ne 1) { throw 'report schema' }"
 $new="    if (`$report.schema_version -ne 3 -or `$report.report_type -cne 'deployment_feasibility' -or `$report.scope.host_control -ne `$false -or `$report.scope.live_volume_access -ne `$false -or `$report.scope.external_network_opt_in -ne `$true) { throw 'report schema' }"
 if(([regex]::Matches($source,[regex]::Escape($old))).Count -ne 1){throw 'SENDER_PATCH'}
 $senderCopy=Join-Path ([IO.Path]::GetDirectoryName($sender)) 'send-feasibility.ps1';[IO.File]::WriteAllText($senderCopy,$source.Replace($old,$new),(New-Object Text.UTF8Encoding($true)))
 if((Invoke-BootstrapChild $senderCopy @{ReportDirectory=$directory;ConfigFile=$config;PrepareOnly=$true} 30) -ne 0){throw 'UPLOAD_PREPARE'}
 if(!(Test-Path -LiteralPath (Join-Path $directory 'upload-receipt.json'))){
  $stage='credential';$helper=Patch-ConsoleCredential (Join-Path $kit 'deploy/docker/club-host-credential.ps1');$tokenFile=Join-Path $kit 'private/report-upload-token.txt'
  Write-Host '報告已保存。請在本終端輸入接收站既有管理員；密碼隱藏，最多等待150秒。'
  if((Invoke-BootstrapChild $helper @{ReportDirectory=$directory;ConfigFile=$config} 150 -Interactive) -ne 0){throw 'CREDENTIAL_FAILED'}
 }
 $stage='upload';$result=Invoke-BootstrapChild $senderCopy @{ReportDirectory=$directory;ConfigFile=$config} 30
 Write-Host ('報告位置：'+$directory)
 if($result -ne 0){Write-Host '回傳未確認；重貼相同完整指令會沿用同一份報告、UUID與operation，不重測。'}
 $global:LASTEXITCODE=$result
}catch{
 $safe=if($stage -cin @('download','workspace','tools','host_preflight','temporary_probe','upload_prepare','credential','upload')){$stage}else{'prepare'}
 Write-Host ('未完成：stage={0}; type={1}。已保存內容保留；不要貼出密碼或token。' -f $safe,$_.Exception.GetType().FullName)
 if($directory){Write-Host ('報告位置：'+$directory)};$global:LASTEXITCODE=2
}finally{
 if($tokenFile -and (Test-Path -LiteralPath $tokenFile -PathType Leaf)){[IO.File]::Delete($tokenFile)}
 if($lock){$lock.Dispose()}
}
}
