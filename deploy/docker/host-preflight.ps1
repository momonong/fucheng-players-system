<#
Read-only Windows deployment preflight. The only default write is a new report
directory under this repository's ignored data/ tree. No container is run.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [string]$InstallPath,
    [ValidateRange(1,20)][int]$TimeoutSeconds = 5,
    [ValidateRange(1,65535)][int]$TestPort = 8052,
    [string]$DockerSubnet = '172.30.98.0/24',
    [string]$ComposeProject,
    [string]$Domain,
    [string]$PreviewOrigin,
    [switch]$ProbeNetwork,
    [string]$DockerExecutable,
    [string]$ImageRef = 'momonong/fucheng-players-system:0.3.0'
)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if (!$InstallPath) { $InstallPath = $repo }
$install = [IO.Path]::GetFullPath($InstallPath)
$data = [IO.Path]::GetFullPath((Join-Path $repo 'data'))
$out = [IO.Path]::GetFullPath($OutputDir)
if (!$out.StartsWith($data + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'OutputDir must be a new directory under the repository ignored data/ directory'
}
if (Test-Path -LiteralPath $out) { throw 'OutputDir already exists; report files are never overwritten' }
if ($ComposeProject -and $ComposeProject -notmatch '^[a-z0-9][a-z0-9_-]{0,62}$') { throw 'Invalid ComposeProject' }
if ($Domain -and $Domain -notmatch '^(?=.{1,253}$)[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]$') { throw 'Invalid domain' }
if ($ImageRef -notmatch '^[a-zA-Z0-9][a-zA-Z0-9./:_@-]{1,255}$') { throw 'Invalid ImageRef' }
if ($PreviewOrigin) {
    $parsed = $null
    if (![Uri]::TryCreate($PreviewOrigin, [UriKind]::Absolute, [ref]$parsed) -or
        $parsed.Scheme -ne 'https' -or $parsed.AbsolutePath -ne '/' -or $parsed.Query -or $parsed.Fragment -or
        $parsed.UserInfo -or $PreviewOrigin.EndsWith('/')) { throw 'PreviewOrigin must be an exact HTTPS origin without a trailing slash' }
}

$checks = New-Object 'System.Collections.Generic.List[object]'
function Add-Check([string]$Id, [string]$Status, [string]$Reason, [string]$Evidence, [string]$NextAction) {
    if ($Status -notin @('PASS','WARN','FAIL','NOT_TESTED')) { throw "Invalid check status: $Status" }
    # All stored prose is generated here, never copied from raw commands or environment values.
    $checks.Add([ordered]@{id=$Id; status=$Status; reason=$Reason; evidence=$Evidence; next_action=$NextAction})
}
function Command-Path([string]$Name) {
    $item = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($item) { return $item.Source }
    return $null
}
function Invoke-Bounded([string]$File, [string]$Arguments, [int]$Limit, [string]$Encoding='utf8') {
    if (!$File -or !(Test-Path -LiteralPath $File -PathType Leaf)) { return @{missing=$true; timed_out=$false; exit_code=$null; stdout=''} }
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $File
    $psi.Arguments = $Arguments
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = if ($Encoding -eq 'unicode') { [Text.Encoding]::Unicode } else { [Text.Encoding]::UTF8 }
    $psi.StandardErrorEncoding = [Text.Encoding]::UTF8
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $psi
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (!$process.WaitForExit($Limit * 1000)) {
            try { $process.Kill() } catch {}
            [void]$process.WaitForExit(1000)
            return @{missing=$false; timed_out=$true; exit_code=$null; stdout=''}
        }
        [void]$stdout.Wait(1000)
        [void]$stderr.Wait(1000)
        return @{missing=$false; timed_out=$false; exit_code=$process.ExitCode; stdout=$stdout.Result.Trim()}
    } catch {
        return @{missing=$false; timed_out=$false; exit_code=$null; stdout=''}
    } finally { $process.Dispose() }
}
function Invoke-LocalBounded([scriptblock]$Block, [object[]]$Arguments, [int]$Limit) {
    $job = $null
    try {
        $job = Start-Job -ScriptBlock $Block -ArgumentList $Arguments -ErrorAction Stop
        if (!(Wait-Job -Job $job -Timeout $Limit)) {
            Stop-Job -Job $job -ErrorAction SilentlyContinue
            return @{timed_out=$true; failed=$false; values=@()}
        }
        return @{timed_out=$false; failed=$false; values=@(Receive-Job -Job $job -ErrorAction Stop)}
    } catch { return @{timed_out=$false; failed=$true; values=@()} }
    finally { if ($job) { Remove-Job -Job $job -Force -ErrorAction SilentlyContinue } }
}
function IPv4-Range([string]$Cidr) {
    if ($Cidr -notmatch '^([0-9.]+)/([0-9]{1,2})$') { return $null }
    $ip = $null
    if (![Net.IPAddress]::TryParse($Matches[1], [ref]$ip) -or $ip.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) { return $null }
    $bits = [int]$Matches[2]
    if ($bits -lt 0 -or $bits -gt 32) { return $null }
    $b = $ip.GetAddressBytes()
    $number = ([double]$b[0]*16777216)+([double]$b[1]*65536)+([double]$b[2]*256)+$b[3]
    $size = [math]::Pow(2, 32-$bits)
    $first = [math]::Floor($number/$size)*$size
    return @{first=$first; last=($first+$size-1)}
}
function Tcp-Probe([string]$HostName, [int]$Port, [int]$Limit) {
    $client = New-Object Net.Sockets.TcpClient
    try {
        $pending = $client.BeginConnect($HostName, $Port, $null, $null)
        if (!$pending.AsyncWaitHandle.WaitOne($Limit*1000)) { return 'timeout' }
        $client.EndConnect($pending)
        return 'connected'
    } catch { return 'failed' }
    finally { $client.Close() }
}
function Dns-Probe([string]$HostName, [int]$Limit) {
    try {
        $task = [Net.Dns]::GetHostAddressesAsync($HostName)
        if (!$task.Wait($Limit*1000)) { return 'timeout' }
        if ($task.Result.Count -eq 0) { return 'empty' }
        return 'resolved'
    } catch { return 'failed' }
}
function Https-Probe([string]$Url, [int]$Limit) {
    $curl = Command-Path 'curl.exe'
    if (!$curl) { return 'missing_curl' }
    $result = Invoke-Bounded $curl "--silent --show-error --max-time $Limit --output NUL --write-out `"%{http_code}|%{ssl_verify_result}`" `"$Url`"" ($Limit+1)
    if ($result.timed_out) { return 'timeout' }
    if ($result.exit_code -ne 0 -or $result.stdout -notmatch '^([0-9]{3})\|0$') { return 'failed' }
    return [int]$Matches[1]
}

$osName = 'unknown'; $osBuild = 'unknown'; $memoryGiB = $null
try {
    $os = Get-CimInstance Win32_OperatingSystem -OperationTimeoutSec $TimeoutSeconds
    $osName = [string]$os.Caption; $osBuild = [string]$os.BuildNumber
    if ($osName -match 'Windows (10|11).*?(Pro|Professional|專業)') {
        Add-Check 'windows_edition' 'PASS' 'Windows Pro edition detected.' "build=$osBuild" 'Confirm Docker Desktop current Windows/WSL support on the club host.'
    } else {
        Add-Check 'windows_edition' 'WARN' 'Windows Pro edition was not confirmed.' "build=$osBuild" 'Verify the exact Windows edition against Docker Desktop requirements.'
    }
} catch { Add-Check 'windows_edition' 'NOT_TESTED' 'Windows OS query unavailable.' 'CIM query failed or timed out.' 'Run from an account allowed to read Win32_OperatingSystem.' }
try {
    $system = Get-CimInstance Win32_ComputerSystem -OperationTimeoutSec $TimeoutSeconds
    $memoryGiB = [math]::Round($system.TotalPhysicalMemory/1GB, 1)
    if ($memoryGiB -ge 8) { Add-Check 'memory' 'PASS' 'Memory meets the 8 GiB Docker Desktop baseline.' "memory_gib=$memoryGiB" 'Check concurrent workload capacity before deployment.' }
    else { Add-Check 'memory' 'WARN' 'Memory is below the 8 GiB baseline.' "memory_gib=$memoryGiB" 'Review Docker Desktop requirements and host capacity.' }
    if ($system.HypervisorPresent) { Add-Check 'virtualization' 'PASS' 'A hypervisor is present.' 'Win32_ComputerSystem.HypervisorPresent=true' 'Confirm WSL 2 backend in Docker Desktop settings.' }
    else {
        $cpu = Get-CimInstance Win32_Processor -OperationTimeoutSec $TimeoutSeconds | Select-Object -First 1
        if ($cpu.VirtualizationFirmwareEnabled -and $cpu.SecondLevelAddressTranslationExtensions) {
            Add-Check 'virtualization' 'PASS' 'Firmware virtualization and SLAT are reported available.' 'CPU capability flags=true' 'Confirm WSL 2 backend in Docker Desktop settings.'
        } else { Add-Check 'virtualization' 'WARN' 'Virtualization/SLAT could not both be confirmed.' 'No hypervisor; one or more CPU flags not true.' 'Check BIOS/UEFI virtualization and WSL requirements.' }
    }
} catch {
    Add-Check 'memory' 'NOT_TESTED' 'Hardware query unavailable.' 'CIM query failed or timed out.' 'Check installed RAM on the club host.'
    Add-Check 'virtualization' 'NOT_TESTED' 'Virtualization query unavailable.' 'CIM query failed or timed out.' 'Check BIOS/UEFI virtualization and WSL 2 support.'
}
try {
    if (!(Test-Path -LiteralPath $install -PathType Container)) { throw 'Install path absent' }
    $root = [IO.Path]::GetPathRoot($install)
    $drive = New-Object IO.DriveInfo($root)
    $freeGiB = [math]::Round($drive.AvailableFreeSpace/1GB, 1)
    $status = if ($freeGiB -ge 20) { 'PASS' } else { 'WARN' }
    Add-Check 'disk_space' $status 'Free space on the installation drive measured.' "free_gib=$freeGiB" 'Reserve capacity for the image, named volume, media and verified off-host backups.'
    if ($install -match '(?i)OneDrive' -or $install.StartsWith('\\')) {
        Add-Check 'install_location' 'WARN' 'Install path appears to be cloud-synced or a network share.' 'Path category only; full path omitted.' 'Use a local disk for Docker data and backups.'
    } else { Add-Check 'install_location' 'PASS' 'Install path appears to be on a local drive.' 'No OneDrive/UNC marker detected.' 'Confirm the actual Docker data root and backup destination separately.' }
} catch {
    Add-Check 'disk_space' 'NOT_TESTED' 'Installation disk could not be measured.' 'Drive query unavailable.' 'Choose an existing local install path and rerun.'
    Add-Check 'install_location' 'NOT_TESTED' 'Installation path could not be classified.' 'Path query unavailable.' 'Choose an existing local install path and rerun.'
}
$backupPath = Join-Path $install 'deploy/docker/backup'
if (Test-Path -LiteralPath $backupPath -PathType Container) {
    Add-Check 'backup_directory' 'PASS' 'Configured example backup directory exists.' 'Directory presence only; no files read.' 'Verify Docker UID 10001 write access with an isolated synthetic backup.'
} else {
    Add-Check 'backup_directory' 'WARN' 'Configured example backup directory does not exist.' 'No directory was created by preflight.' 'Create a new backup directory during setup; keep it outside Git and export off-host.'
}
Add-Check 'backup_write_and_restore' 'NOT_TESTED' 'Read-only preflight cannot prove container UID write access or recovery.' 'No volume or backup modified.' 'Run isolated synthetic backup, export/hash and new-target restore.'
Add-Check 'docker_data_root' 'NOT_TESTED' 'Install drive free space does not identify Docker Desktop volume storage.' 'No Docker Desktop settings file opened.' 'Confirm the Docker data root drive, capacity and backup destination on the club host.'

$wsl = Command-Path 'wsl.exe'
$wslResult = Invoke-Bounded $wsl '--version' $TimeoutSeconds 'unicode'
if ($wslResult.missing) { Add-Check 'wsl_version' 'FAIL' 'wsl.exe is unavailable.' 'Command missing.' 'Install or update WSL 2 using Microsoft instructions.' }
elseif ($wslResult.timed_out) { Add-Check 'wsl_version' 'NOT_TESTED' 'WSL version command timed out.' "timeout_s=$TimeoutSeconds" 'Inspect WSL health manually; rerun with a fresh output directory.' }
elseif ($wslResult.exit_code -ne 0) { Add-Check 'wsl_version' 'WARN' 'WSL version could not be read.' "exit_code=$($wslResult.exit_code)" 'Run wsl.exe --version manually; update if required.' }
else {
    $match = [regex]::Match($wslResult.stdout, '(?im)^\s*WSL\s*(?:version|版本)\s*[:：]\s*([0-9.]+)')
    if ($match.Success) {
        $version = $match.Groups[1].Value
        try {
            if ([version]$version -ge [version]'2.1.5') { Add-Check 'wsl_version' 'PASS' 'WSL version meets the Docker Desktop baseline.' "wsl_version=$version" 'Confirm Docker Desktop is configured for the WSL 2 Linux engine.' }
            else { Add-Check 'wsl_version' 'WARN' 'WSL version is below the Docker Desktop baseline.' "wsl_version=$version" 'Update WSL before installing the app.' }
        } catch { Add-Check 'wsl_version' 'WARN' 'WSL version format could not be compared.' 'Version parser rejected numeric text.' 'Check wsl.exe --version manually.' }
    } else { Add-Check 'wsl_version' 'NOT_TESTED' 'WSL command ran, but its version format was not recognized.' 'Exit code 0; raw output intentionally omitted.' 'Check wsl.exe --version manually.' }
}
Add-Check 'wsl_backend' 'NOT_TESTED' 'WSL availability does not identify the Docker Desktop backend.' 'No settings or credentials file read.' 'In Docker Desktop verify WSL 2 backend and Linux containers.'

try {
    $portProbe = Invoke-LocalBounded { param($port) Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -eq $port } @($TestPort) $TimeoutSeconds
    if ($portProbe.failed -or $portProbe.timed_out) { throw 'Port probe unavailable' }
    $listeners = @($portProbe.values)
    if ($listeners.Count) {
        $loopbackOnly = @($listeners | Where-Object { $_.LocalAddress -notin @('127.0.0.1','::1') }).Count -eq 0
        $scope = if ($loopbackOnly) { 'loopback only' } else { 'includes a non-loopback bind' }
        Add-Check 'test_port' 'WARN' "Port $TestPort is already in use ($scope)." "listener_count=$($listeners.Count)" 'Identify the owner before choosing a project port; do not stop an unknown service.'
    } else { Add-Check 'test_port' 'PASS' "Port $TestPort has no local listener." 'TCP listener query returned zero.' 'Recheck immediately before binding the deployment.' }
} catch { Add-Check 'test_port' 'NOT_TESTED' 'Local listener query was denied or unavailable.' 'Get-NetTCPConnection failed.' 'Check port ownership with an authorized local account.' }
try {
    $directProbe = Invoke-LocalBounded { Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalPort -in @(80,443) } } @() $TimeoutSeconds
    if ($directProbe.failed -or $directProbe.timed_out) { throw 'Direct port probe unavailable' }
    $occupied = @($directProbe.values | Select-Object -ExpandProperty LocalPort -Unique)
    if ($occupied.Count) { Add-Check 'direct_ports' 'WARN' 'One or both local direct TLS ports are occupied.' "occupied_80_443_count=$($occupied.Count)" 'Identify the owner before evaluating Caddy/nginx; do not stop it automatically.' }
    else { Add-Check 'direct_ports' 'PASS' 'No local listeners found on 80/443.' 'Local port availability only.' 'External 80/443 reachability remains untested.' }
} catch { Add-Check 'direct_ports' 'NOT_TESTED' 'Local 80/443 listener query was unavailable.' 'Bounded Get-NetTCPConnection failed.' 'Check local port ownership manually.' }
try {
    $service = Get-CimInstance Win32_Service -Filter "Name='com.docker.service'" -OperationTimeoutSec $TimeoutSeconds
    if ($service) {
        $serviceStatus = if ($service.State -eq 'Running' -and $service.StartMode -eq 'Auto') { 'PASS' } else { 'WARN' }
        Add-Check 'docker_service' $serviceStatus 'Docker Desktop service record was found; this alone does not prove unattended startup.' "state=$($service.State); start_mode=$($service.StartMode)" 'Verify actual recovery after a Windows reboot and designated user sign-in.'
    }
    else { Add-Check 'docker_service' 'NOT_TESTED' 'Docker Desktop service not found; per-user WSL installation may differ.' 'No service record.' 'Inspect the Docker Desktop installation and startup policy.' }
} catch { Add-Check 'docker_service' 'NOT_TESTED' 'Docker service query unavailable.' 'CIM query failed or timed out.' 'Inspect Docker Desktop startup policy manually.' }
$powercfg = Command-Path 'powercfg.exe'
$sleep = Invoke-Bounded $powercfg '/query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE' $TimeoutSeconds
if ($sleep.missing -or $sleep.timed_out -or $sleep.exit_code -ne 0) {
    Add-Check 'ac_sleep' 'NOT_TESTED' 'AC sleep policy could not be read.' 'Missing, timed-out, or failed powercfg command.' 'Review Windows AC sleep, hibernate and power-loss recovery settings.'
} else {
    $values = @([regex]::Matches($sleep.stdout, '0x[0-9a-fA-F]{8}') | ForEach-Object Value)
    if ($values.Count -ge 2) {
        $ac = [convert]::ToInt64($values[$values.Count-2].Substring(2),16)
        if ($ac -eq 0) { Add-Check 'ac_sleep' 'PASS' 'Current AC sleep timeout is disabled.' 'powercfg AC index=0' 'Still test real power loss, reboot and Docker Desktop sign-in recovery.' }
        else { Add-Check 'ac_sleep' 'WARN' 'Current AC sleep timeout is nonzero.' "powercfg_ac_seconds=$ac" 'Disable unattended sleep for the deployment host under approved local policy.' }
    } else { Add-Check 'ac_sleep' 'NOT_TESTED' 'Power settings output could not be parsed.' 'Raw powercfg output intentionally omitted.' 'Review AC sleep in Windows Settings.' }
}
Add-Check 'cold_boot_recovery' 'NOT_TESTED' 'Running processes and restart policies do not prove unattended cold-boot recovery.' 'No reboot or sign-in performed.' 'Test power recovery, Windows sign-in, Docker Desktop start, app/backup and public URL at the club.'
Add-Check 'hibernate_policy' 'NOT_TESTED' 'AC sleep timeout does not establish hibernate, lid, update or power-loss behavior.' 'No power state was changed.' 'Review hibernate/Windows Update policy and perform a controlled recovery drill.'
try {
    $firewallProbe = Invoke-LocalBounded { Get-NetFirewallProfile -ErrorAction Stop } @() $TimeoutSeconds
    if ($firewallProbe.failed -or $firewallProbe.timed_out) { throw 'Firewall probe unavailable' }
    $profiles = @($firewallProbe.values)
    if ($profiles.Count) {
        $blocked = @($profiles | Where-Object { $_.DefaultOutboundAction -eq 'Block' }).Count
        $status = if ($blocked) { 'WARN' } else { 'PASS' }
        Add-Check 'windows_firewall_baseline' $status 'Windows firewall profile defaults were read.' "profiles=$($profiles.Count); outbound_block_profiles=$blocked" 'Check effective outbound rules and upstream network policy for the selected tunnel.'
    } else { Add-Check 'windows_firewall_baseline' 'NOT_TESTED' 'No firewall profiles returned.' 'Profile query empty.' 'Check Windows firewall and site policy manually.' }
} catch { Add-Check 'windows_firewall_baseline' 'NOT_TESTED' 'Firewall profile query unavailable.' 'Get-NetFirewallProfile failed.' 'Check local policy with an authorized account.' }
$proxyPresent = [bool]($env:HTTP_PROXY -or $env:HTTPS_PROXY -or $env:ALL_PROXY)
Add-Check 'proxy_configuration' 'WARN' 'Proxy presence is recorded without reading credentials or URLs.' "process_proxy_env_present=$($proxyPresent.ToString().ToLowerInvariant())" 'Confirm whether Docker Desktop, registry and tunnel traffic use an approved proxy.'
Add-Check 'firewall_egress_policy' 'NOT_TESTED' 'Local profile defaults do not prove site firewall or proxy egress.' 'No firewall rule or network policy changed.' 'Have the site owner check 7844 TCP/UDP, HTTPS and registry paths.'

$docker = if ($DockerExecutable) { $DockerExecutable } else { Command-Path 'docker.exe' }
$dockerInfo = Invoke-Bounded $docker 'info --format "{{.OSType}}|{{.Architecture}}|{{.ServerVersion}}"' $TimeoutSeconds
$dockerReady = $false; $dockerPlatform = 'unknown'; $dockerVersion = 'unknown'
if ($dockerInfo.missing) { Add-Check 'docker_engine' 'FAIL' 'Docker CLI is unavailable.' 'Command missing.' 'Install/start Docker Desktop Linux engine, then rerun.' }
elseif ($dockerInfo.timed_out) { Add-Check 'docker_engine' 'NOT_TESTED' 'Docker daemon query timed out.' "timeout_s=$TimeoutSeconds" 'Inspect Docker Desktop engine state; do not restart unrelated workloads automatically.' }
elseif ($dockerInfo.exit_code -ne 0) { Add-Check 'docker_engine' 'FAIL' 'Docker CLI could not reach a usable daemon.' "exit_code=$($dockerInfo.exit_code)" 'Start/repair Docker Desktop with the service owner; preserve existing containers and volumes.' }
elseif ($dockerInfo.stdout -match '^(linux|windows)\|([a-zA-Z0-9_/-]+)\|([a-zA-Z0-9_.+-]+)$') {
    $dockerPlatform = "$($Matches[1])/$($Matches[2])"; $dockerVersion=$Matches[3]; $dockerReady=$true
    if ($dockerPlatform -in @('linux/x86_64','linux/amd64')) { Add-Check 'docker_engine' 'PASS' 'Linux amd64 Docker engine is reachable.' "platform=$dockerPlatform; server_version=$dockerVersion" 'Verify image and isolated Compose project next.' }
    else { Add-Check 'docker_engine' 'FAIL' 'Docker engine platform is not Linux amd64.' "platform=$dockerPlatform" 'Switch to a compatible Linux container engine before using this image.' }
} else { Add-Check 'docker_engine' 'WARN' 'Docker info returned an unrecognized format.' 'Raw output intentionally omitted.' 'Run docker info locally and confirm linux/amd64.' }
if ($dockerReady) {
    $compose = Invoke-Bounded $docker 'compose version --short' $TimeoutSeconds
    if (!$compose.timed_out -and $compose.exit_code -eq 0 -and $compose.stdout -match '^v?[0-9]+\.[0-9]+') { Add-Check 'compose_plugin' 'PASS' 'Docker Compose plugin is available.' "compose_version=$($compose.stdout.Split("`n")[0])" 'Use the pinned Compose files from the same release.' }
    else { Add-Check 'compose_plugin' 'FAIL' 'Docker Compose plugin was not confirmed.' 'Missing, failed, timed out or malformed version output.' 'Install/update the Docker Desktop Compose plugin.' }
    $image = Invoke-Bounded $docker "image inspect --format `"{{.Os}}|{{.Architecture}}`" `"$ImageRef`"" $TimeoutSeconds
    if (!$image.timed_out -and $image.exit_code -eq 0 -and $image.stdout -eq 'linux|amd64') { Add-Check 'app_image' 'PASS' 'Local app image is Linux amd64.' 'Image platform=linux/amd64; no pull performed.' 'Verify the published digest before an authorized install.' }
    elseif ($image.timed_out) { Add-Check 'app_image' 'NOT_TESTED' 'Image inspection timed out.' "timeout_s=$TimeoutSeconds" 'Inspect the pinned image locally.' }
    else { Add-Check 'app_image' 'WARN' 'Pinned app image was not confirmed locally.' 'Missing image or unexpected platform; raw CLI output omitted.' 'Pull the reviewed image digest, then rerun.' }
    $candidate = IPv4-Range $DockerSubnet
    if (!$candidate) { Add-Check 'docker_subnet' 'WARN' 'Proposed DockerSubnet is not valid IPv4 CIDR.' 'Subnet parser rejected input.' 'Choose a valid isolated subnet.' }
    else {
        $ids = Invoke-Bounded $docker 'network ls -q' $TimeoutSeconds
        if ($ids.timed_out -or $ids.exit_code -ne 0) { Add-Check 'docker_subnet' 'NOT_TESTED' 'Docker networks could not be enumerated.' 'Network listing failed or timed out.' 'Check overlap before Compose up.' }
        else {
            $networkIds = @($ids.stdout -split '\s+' | Where-Object { $_ -match '^[a-f0-9]{12,64}$' })
            if ($networkIds.Count -gt 30) { Add-Check 'docker_subnet' 'NOT_TESTED' 'More than 30 Docker networks require manual inventory.' 'Probe capped at 30 networks.' 'Check proposed subnet against all networks and LAN/VPN routes.' }
            elseif ($networkIds.Count -eq 0) { Add-Check 'docker_subnet' 'PASS' 'No existing Docker networks were returned.' 'Docker network count=0.' 'Still compare the subnet with LAN/VPN routes.' }
            else {
                $details = Invoke-Bounded $docker ("network inspect --format `"{{range .IPAM.Config}}{{.Subnet}} {{end}}`" " + ($networkIds -join ' ')) $TimeoutSeconds
                if ($details.timed_out -or $details.exit_code -ne 0) { Add-Check 'docker_subnet' 'NOT_TESTED' 'Docker network subnets could not be inspected.' 'Network inspect failed or timed out.' 'Check overlap before Compose up.' }
                else {
                    $overlaps=0
                    foreach ($cidr in ([regex]::Matches($details.stdout, '\b(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}\b') | ForEach-Object Value)) {
                        $range=IPv4-Range $cidr
                        if ($range -and $range.first -le $candidate.last -and $candidate.first -le $range.last) { $overlaps++ }
                    }
                    if ($overlaps) { Add-Check 'docker_subnet' 'WARN' 'Proposed subnet overlaps an existing Docker network.' "docker_network_count=$($networkIds.Count); overlap_count=$overlaps" 'Choose a new subnet before creating another Compose project.' }
                    else { Add-Check 'docker_subnet' 'PASS' 'No overlap found in inspected Docker networks.' "docker_network_count=$($networkIds.Count); overlap_count=0" 'Check LAN/VPN routes separately before deployment.' }
                }
            }
        }
    }
    if ($ComposeProject) {
        $project = Invoke-Bounded $docker "ps -a --filter `"label=com.docker.compose.project=$ComposeProject`" --format `"{{.Names}}|{{.Status}}`"" $TimeoutSeconds
        if ($project.timed_out -or $project.exit_code -ne 0) { Add-Check 'project_health' 'NOT_TESTED' 'Compose project status could not be read.' 'Docker ps failed or timed out.' 'Inspect only the named project manually.' }
        else {
            $rows = @($project.stdout -split "`n" | Where-Object { $_ -match '^[a-zA-Z0-9_.-]+\|' })
            if ($rows.Count -eq 0) { Add-Check 'project_health' 'NOT_TESTED' 'Named Compose project has no containers yet.' 'Project filter returned zero.' 'Run an isolated synthetic install only after preflight review.' }
            elseif ($rows.Count -gt 10) { Add-Check 'project_health' 'WARN' 'Project has more than 10 containers; bounded inspect skipped.' "container_count=$($rows.Count)" 'Inspect project ownership and expected services manually.' }
            else {
                $healthy = @($rows | Where-Object { $_ -match 'Up.*\(healthy\)' }).Count
                $running = @($rows | Where-Object { $_ -match '\|Up ' }).Count
                $restartIssues = 0
                foreach ($row in $rows) {
                    $name = $row.Split('|')[0]
                    $restart = Invoke-Bounded $docker "inspect --format `"{{.HostConfig.RestartPolicy.Name}}`" $name" $TimeoutSeconds
                    if ($restart.timed_out -or $restart.exit_code -ne 0 -or $restart.stdout -notin @('unless-stopped','always')) { $restartIssues++ }
                }
                $state = if ($running -eq $rows.Count -and $restartIssues -eq 0) { 'PASS' } else { 'WARN' }
                Add-Check 'project_health' $state 'Only the named Compose project was inspected.' "containers=$($rows.Count); running=$running; healthy_reported=$healthy; restart_policy_issues=$restartIssues" 'Check app/backup health and the public URL; restart policy is not cold-boot proof.'
            }
        }
    } else { Add-Check 'project_health' 'NOT_TESTED' 'No ComposeProject was supplied.' 'No container names or volumes inspected.' 'After an isolated trial, rerun with -ComposeProject.' }
} else {
    foreach ($id in @('compose_plugin','app_image','docker_subnet','project_health')) {
        Add-Check $id 'NOT_TESTED' 'Docker-dependent probe skipped because the engine is unavailable.' 'No containers or volumes touched.' 'Restore Docker access, then rerun with a new report directory.'
    }
}
Add-Check 'lan_vpn_subnet' 'NOT_TESTED' 'Docker network comparison does not prove LAN/VPN route compatibility.' 'No LAN scan or route modification.' 'Compare the chosen subnet with actual LAN/VPN routes on the club host.'

if ($ProbeNetwork) {
    if ($Domain) {
        $dns = Dns-Probe $Domain $TimeoutSeconds
        if ($dns -eq 'resolved') { Add-Check 'domain_dns' 'PASS' 'The provided domain resolves from this host.' 'Address count and values omitted.' 'Confirm domain ownership and DNS from an external network.' }
        else { Add-Check 'domain_dns' 'WARN' 'The provided domain did not resolve within the bound.' "dns_result=$dns" 'Check DNS and domain ownership with the site owner.' }
    } else { Add-Check 'domain_dns' 'NOT_TESTED' 'No domain was supplied.' 'No DNS query sent.' 'Provide an approved public hostname for a later network probe.' }
    $cf1 = Tcp-Probe 'region1.v2.argotunnel.com' 7844 $TimeoutSeconds
    $cf2 = Tcp-Probe 'region2.v2.argotunnel.com' 7844 $TimeoutSeconds
    if ($cf1 -eq 'connected' -and $cf2 -eq 'connected') { Add-Check 'cloudflare_tcp_7844' 'PASS' 'Direct TCP 7844 connected to both documented Cloudflare regions from this host.' 'region1/region2.v2.argotunnel.com:7844; direct TCP only.' 'Validate the actual cloudflared HTTP/2 tunnel and site policy; UDP remains untested.' }
    else { Add-Check 'cloudflare_tcp_7844' 'WARN' 'Direct TCP 7844 was not confirmed for both regions.' "region1=$cf1; region2=$cf2" 'Check firewall/proxy policy and test Cloudflare Tunnel on the club network.' }
    Add-Check 'cloudflare_udp_7844' 'NOT_TESTED' 'TCP success does not prove QUIC/UDP availability.' 'No UDP tunnel handshake was attempted.' 'Test cloudflared QUIC or obtain site firewall evidence for UDP 7844.'
    $https = Https-Probe 'https://www.cloudflare.com/cdn-cgi/trace' $TimeoutSeconds
    if ($https -is [int] -and $https -ge 200 -and $https -lt 500) { Add-Check 'cloudflare_https' 'PASS' 'Cloudflare HTTPS completed with certificate verification.' "http_status=$https" 'This does not prove TCP/UDP 7844 or Tunnel credentials.' }
    else { Add-Check 'cloudflare_https' 'WARN' 'Cloudflare HTTPS was not confirmed.' "probe_result=$https" 'Check HTTPS/proxy/CA path without disabling TLS verification.' }
    $registry = Https-Probe 'https://registry-1.docker.io/v2/' $TimeoutSeconds
    if ($registry -is [int] -and $registry -in @(200,401)) { Add-Check 'registry_https' 'PASS' 'Docker registry HTTPS and certificate path responded.' "http_status=$registry" 'Verify docker pull with the reviewed digest during an authorized isolated install.' }
    else { Add-Check 'registry_https' 'WARN' 'Registry HTTPS was not confirmed.' "probe_result=$registry" 'Check proxy/registry policy; do not change daemon settings automatically.' }
    $ngrok = Tcp-Probe 'connect.ngrok-agent.com' 443 $TimeoutSeconds
    if ($ngrok -eq 'connected') { Add-Check 'ngrok_tcp_443' 'PASS' 'Direct TCP to the ngrok agent endpoint succeeded.' 'connect.ngrok-agent.com:443; no auth or tunnel attempted.' 'Verify a real ngrok session within the account limit.' }
    else { Add-Check 'ngrok_tcp_443' 'WARN' 'Direct TCP to ngrok was not confirmed.' "tcp_result=$ngrok" 'Check site proxy/firewall policy before the trial.' }
    if ($PreviewOrigin) {
        $preview = Https-Probe "$PreviewOrigin/api/health" $TimeoutSeconds
        if ($preview -eq 200) { Add-Check 'preview_https' 'PASS' 'HTTPS health responded from this host with TLS verification.' 'HTTP 200; no credentials sent.' 'Verify again from a phone on a different network; this is not external ingress proof.' }
        else { Add-Check 'preview_https' 'WARN' 'Preview HTTPS health did not return 200.' "probe_result=$preview" 'Inspect only the named preview and tunnel owner.' }
    } else { Add-Check 'preview_https' 'NOT_TESTED' 'No PreviewOrigin was supplied.' 'No preview request sent.' 'After the authorized trial, rerun with the exact HTTPS origin.' }
} else {
    foreach ($id in @('domain_dns','cloudflare_tcp_7844','cloudflare_udp_7844','cloudflare_https','registry_https','ngrok_tcp_443','preview_https')) {
        Add-Check $id 'NOT_TESTED' 'External network probing was not requested.' 'Default preflight made no external network request.' 'Rerun with -ProbeNetwork on the intended network if authorized.'
    }
}
Add-Check 'domain_control' 'NOT_TESTED' 'Domain ownership, DNS administration and tunnel keys were not inspected.' 'No account or secret file opened.' 'Confirm domain/control-plane access separately; do not paste tokens into reports.'
Add-Check 'public_ingress' 'NOT_TESTED' 'Local DNS/TCP/port checks cannot prove public inbound reachability.' 'No external vantage or router/ISP configuration examined.' 'Test from another network and confirm routing/firewall; a private LAN IP alone does not prove CGNAT.'
Add-Check 'direct_tls' 'NOT_TESTED' 'Caddy/nginx direct TLS cannot be selected from local checks alone.' 'External 80/443, DNS, cert storage and renewal unverified.' 'If choosing direct ingress, validate public DNS and 80/443; DNS-01 alone does not expose the site.'

function Check-Status([string]$Id) {
    foreach ($check in $checks) { if ($check.id -eq $Id) { return $check.status } }
    return 'NOT_TESTED'
}
$cfStatus = if ((Check-Status 'cloudflare_tcp_7844') -eq 'PASS' -and (Check-Status 'cloudflare_https') -eq 'PASS') { 'WARN' } else { 'NOT_TESTED' }
$cfReason = if ($cfStatus -eq 'WARN') { '此主機的 TCP 7844 與 HTTPS 探測通過；UDP/QUIC、網域、憑證及真正 cloudflared 連線仍未驗證。' } else { '出站 Tunnel 候選；目前不足以判定站點網路與 Cloudflare 帳號條件。' }
$ngrokStatus = if ((Check-Status 'preview_https') -eq 'PASS') { 'WARN' } else { 'NOT_TESTED' }
$ngrokReason = if ($ngrokStatus -eq 'WARN') { '從本主機連回指定 HTTPS 預覽成功；不等於其他網路的手機可達或帳號可開第二個 agent。' } else { '可作合成試用；尚無當次 HTTPS 預覽證據或外部手機證據。' }
$recommendations = @(
    [ordered]@{candidate='Cloudflare Tunnel 直連 app'; status=$cfStatus; reason="${cfReason}這是出站公開入口，不需公網入站 IP；既有單 app 架構可優先評估。"; next_action='核對網域控制、7844 TCP/UDP、HTTPS 與隔離 Tunnel；不切換現用入口。'},
    [ordered]@{candidate='ngrok 合成試用'; status=$ngrokStatus; reason=$ngrokReason; next_action='保留隔離預覽，比對部署前後報告，再用另一網路的手機測試。'},
    [ordered]@{candidate='Caddy 直連 TLS'; status='NOT_TESTED'; reason='Reverse proxy，可與 Tunnel 組合。HTTP-01/TLS-ALPN-01 分別需要外部 80/443 可達；DNS-01 只解決簽證。'; next_action='有網域、DNS、外部入站證據與持久憑證目錄後再比較。'},
    [ordered]@{candidate='nginx 直連 TLS'; status='NOT_TESTED'; reason='Reverse proxy，可與 Tunnel 組合；需另設憑證申請與續期。原生 Windows nginx 的限制不可套用到 Docker Linux nginx。'; next_action='直連前置條件成立後再比較憑證流程。'}
)
$counts = [ordered]@{PASS=0; WARN=0; FAIL=0; NOT_TESTED=0}
foreach ($check in $checks) { $counts[$check.status]++ }
$report = [ordered]@{
    schema_version=1
    checked_at=(Get-Date).ToString('o')
    host=[ordered]@{name=$env:COMPUTERNAME; windows=$osName; build=$osBuild; install_drive_free_gib=$freeGiB; docker_platform=$dockerPlatform; docker_server_version=$dockerVersion}
    scope=[ordered]@{read_only_probes=$true; created_report_directory=$true; external_network_opt_in=[bool]$ProbeNetwork; container_execution=$false; live_volume_access=$false; compose_project=if($ComposeProject){$ComposeProject}else{$null}; test_port=$TestPort; proposed_docker_subnet=$DockerSubnet}
    summary=$counts
    checks=$checks.ToArray()
    recommendations=$recommendations
    sources=@('https://docs.docker.com/desktop/setup/install/windows-install/', 'https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/', 'https://caddyserver.com/docs/automatic-https', 'https://nginx.org/en/docs/windows.html')
}
$lines = New-Object 'System.Collections.Generic.List[string]'
$lines.Add('# Windows Docker 主機部署前健檢')
$lines.Add('')
$lines.Add("- 時間：$($report.checked_at)")
$lines.Add("- 主機：$($report.host.name)；系統：$osName build $osBuild")
$lines.Add("- 範圍：唯讀主機／Docker CLI 檢查；建立本報告目錄；外部網路探測=$([bool]$ProbeNetwork)；容器執行=false；live volume 存取=false")
$lines.Add("- 計數：PASS $($counts.PASS)、WARN $($counts.WARN)、FAIL $($counts.FAIL)、NOT_TESTED $($counts.NOT_TESTED)")
$lines.Add('')
$lines.Add('檢查結果僅代表這部主機與執行時間；不等於球館實際外部可達、正式資料或部署批准。')
$lines.Add('')
$lines.Add('| 檢查 | 狀態 | 理由與證據 | 下一步 |')
$lines.Add('| --- | --- | --- | --- |')
$zh = @{
    windows_edition=@('Windows 版本','核對本機 Windows 版本與 build。','到球館主機核對 Windows Pro 及 Docker Desktop 支援版本。')
    memory=@('記憶體','核對 Docker Desktop 基本記憶體容量。','再評估與其他工作負載同時執行的餘裕。')
    virtualization=@('虛擬化','核對 Hypervisor 或 CPU 的虛擬化與 SLAT 訊號。','到 Docker Desktop 畫面確認 WSL 2 backend。')
    disk_space=@('磁碟空間','量測安裝路徑所在磁碟的可用空間。','保留 image、volume、媒體與異地備份所需容量。')
    install_location=@('安裝位置','檢查路徑是否疑似 OneDrive 或網路共享。','正式資料與備份使用受管理的本機磁碟。')
    backup_directory=@('備份目錄','檢查範例 host 備份目錄是否存在。','部署時建立獨立且不入 Git 的備份目錄。')
    backup_write_and_restore=@('備份可寫與還原','唯讀健檢無法證明容器 UID 可寫或備份可還原。','以隔離合成資料執行 backup、匯出驗 hash 與新目標還原。')
    docker_data_root=@('Docker 資料根目錄','安裝磁碟空間不等於 Docker volume 所在磁碟容量。','到 Docker Desktop 核對資料根目錄與剩餘容量。')
    wsl_version=@('WSL 版本','核對 WSL 版本是否滿足 Docker Desktop 前置需求。','缺失或版本過舊時先安裝／更新 WSL。')
    wsl_backend=@('Docker WSL backend','WSL 可用不代表 Docker Desktop 已選 WSL 2。','在 Docker Desktop 設定確認 WSL 2 與 Linux containers。')
    test_port=@('試用埠','檢查指定本機埠的 listener。','占用時先查 owner，不停止未知服務。')
    direct_ports=@('本機 80／443','只檢查本機 80／443 是否已有 listener。','考慮直連 TLS 時再做外部入站驗證。')
    docker_service=@('Docker 服務','服務存在或啟動模式不證明無人登入冷開機可恢復。','到球館主機實測重開機、登入及 Docker Desktop 恢復。')
    ac_sleep=@('AC 休眠','核對目前 AC 電源睡眠逾時。','依場地政策核對休眠與斷電後恢復。')
    cold_boot_recovery=@('冷開機恢復','本次沒有執行重啟或登入流程。','在球館主機驗 Docker、app、backup 與公開網址恢復。')
    hibernate_policy=@('休眠與更新政策','AC 睡眠逾時不涵蓋 hibernate、更新或斷電。','核對政策並做受控恢復演練。')
    windows_firewall_baseline=@('Windows 防火牆概況','只讀取防火牆 profile 預設狀態。','另核對有效規則及場地出口防火牆。')
    proxy_configuration=@('Proxy 線索','只記錄程序 proxy 環境變數是否存在，不讀取值。','由場地管理者核對 Docker、registry 與 Tunnel 所用 proxy。')
    firewall_egress_policy=@('出口政策','本機預設規則不證明場地防火牆可出站。','核對 7844 TCP／UDP、HTTPS 與 registry 政策。')
    docker_engine=@('Docker engine','核對 daemon 可達與 Linux amd64 平台。','不可用時由 owner 處理 Docker Desktop；勿重啟不相關服務。')
    compose_plugin=@('Compose plugin','核對 Docker Compose plugin 可用性。','使用與 image 相容且固定版本的 Compose 設定。')
    app_image=@('本機 app image','只讀檢查已下載 image 的平台，不拉取。','部署時拉取並核對已審核的固定 digest。')
    docker_subnet=@('Docker 網段','只比對指定 subnet 與已存在 Docker networks。','再核對球館 LAN／VPN 路由後選唯一 subnet。')
    project_health=@('指定 project 健康','只查指定 Compose project 的容器狀態與 restart policy。','再驗 app／backup 與手機公開入口；restart policy 不保證冷開機。')
    lan_vpn_subnet=@('LAN／VPN 網段','Docker networks 不足以推論 LAN／VPN 是否衝突。','由場地管理者核對實際路由。')
    domain_dns=@('網域 DNS','只檢查從本主機解析指定網域。','另核對網域控制權與外部網路 DNS。')
    cloudflare_tcp_7844=@('Cloudflare TCP 7844','只測兩個官方 region 的直接 TCP 連線。','再核對實際 cloudflared HTTP/2 與場地政策。')
    cloudflare_udp_7844=@('Cloudflare UDP 7844','TCP 成功不能證明 QUIC／UDP 可用。','用隔離 cloudflared 或場地防火牆證據核對 UDP。')
    cloudflare_https=@('Cloudflare HTTPS','只核對官方 HTTPS 端點與 TLS。','不要以 HTTPS 成功代替 7844 或 Tunnel 金鑰驗證。')
    registry_https=@('Docker Registry HTTPS','只核對 registry HTTPS／TLS 回應。','實際安裝時再 docker pull 固定 digest。')
    ngrok_tcp_443=@('ngrok TCP 443','只測 agent 端點 TCP，沒有認證或開 Tunnel。','核對帳號 session 配額及實際 ngrok 試用。')
    preview_https=@('預覽 HTTPS','只從本主機對指定 health 做免憑證 HTTPS 請求。','另用不同網路的手機檢查可達與功能。')
    domain_control=@('網域／金鑰控制','未讀取帳號或密鑰檔。','由擁有者核對 domain、DNS 與 Tunnel token。')
    public_ingress=@('公網入站','本機 DNS／port／回連不證明公網可達；私有 LAN IP 不等於 CGNAT。','從另一網路測試並核對路由、防火牆與 ISP。')
    direct_tls=@('直連 TLS','尚無足夠證據選 Caddy 或 nginx 直連。','先核對外部 80／443、DNS、憑證儲存與續期。')
}
foreach ($check in $checks) {
    $presentation = $zh[$check.id]
    if (!$presentation) { throw "Missing report presentation for $($check.id)" }
    $detail = "$($presentation[1]) 證據：$($check.evidence)".Replace('|','/').Replace("`n",' ')
    $next = $presentation[2].Replace('|','/').Replace("`n",' ')
    $lines.Add("| $($presentation[0]) ($($check.id)) | $($check.status) | $detail | $next |")
}
$lines.Add('')
$lines.Add('## 入口比較與建議')
$lines.Add('')
foreach ($item in $recommendations) {
    $lines.Add("- **$($item.candidate)（$($item.status)）**：$($item.reason) 下一步：$($item.next_action)")
}
$lines.Add('')
$lines.Add('## 官方契約')
$lines.Add('')
foreach ($url in $report.sources) { $lines.Add("- $url") }
New-Item -ItemType Directory -Path $out -Force | Out-Null
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText((Join-Path $out 'report.json'), (($report | ConvertTo-Json -Depth 8) + "`n"), $utf8)
[IO.File]::WriteAllText((Join-Path $out 'report.md'), (($lines -join "`n") + "`n"), $utf8)
Write-Output "Report: $out"
Write-Output "PASS=$($counts.PASS) WARN=$($counts.WARN) FAIL=$($counts.FAIL) NOT_TESTED=$($counts.NOT_TESTED)"
