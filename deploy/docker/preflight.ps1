param([int]$TestPort=8447, [string]$Output, [string]$InstallPath)
$ErrorActionPreference='Stop'
if (!$InstallPath) { $InstallPath = Split-Path -Parent $MyInvocation.MyCommand.Path }
$issues = [Collections.Generic.List[string]]::new()
function Probe([scriptblock]$Command) { try { & $Command } catch { "UNAVAILABLE: $($_.Exception.Message)" } }
function Read-Wsl([string]$Arguments) {
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = 'wsl.exe'
    $start.Arguments = $Arguments
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.StandardOutputEncoding = [Text.Encoding]::Unicode
    $process = [Diagnostics.Process]::Start($start)
    $value = $process.StandardOutput.ReadToEnd()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw 'WSL command failed' }
    $value
}
$os = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$computer = Get-CimInstance Win32_ComputerSystem
$drive = Get-PSDrive -Name ([IO.Path]::GetPathRoot([IO.Path]::GetFullPath($InstallPath)).Substring(0,1))
$listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -eq $TestPort | Select-Object LocalAddress,LocalPort,OwningProcess)
if ($listeners.Count) { $issues.Add("Test port $TestPort is occupied; do not stop unknown services") }
if (!$cpu.VirtualizationFirmwareEnabled -and !$computer.HypervisorPresent) { $issues.Add('Firmware virtualization not confirmed') }
if ($drive.Free -lt 20GB) { $issues.Add('Less than 20 GiB free; review Docker/backup capacity') }
if ($InstallPath -match 'OneDrive|^\\\\') { $issues.Add('Do not use OneDrive or network storage for live SQLite or Docker data') }
$result = [ordered]@{
    checked_at=(Get-Date).ToString('o'); host=$env:COMPUTERNAME
    windows=$os.Caption; build=$os.BuildNumber; memory_gib=[math]::Round($computer.TotalPhysicalMemory/1GB,1)
    virtualization=$cpu.VirtualizationFirmwareEnabled; slat=$cpu.SecondLevelAddressTranslationExtensions; hypervisor=$computer.HypervisorPresent
    free_gib=[math]::Round($drive.Free/1GB,1); port=$TestPort; listeners=$listeners
    wsl=Probe { Read-Wsl '--version' }
    wsl_distributions=Probe { Read-Wsl '--list --verbose' }
    docker=Probe { (& docker version --format '{{json .}}' 2>&1) -join "`n" }
    compose=Probe { (& docker compose version 2>&1) -join "`n" }
    networks=Probe { (& docker network ls --format '{{.Name}}' 2>&1) -join "`n" }
    server_service=Probe { Get-CimInstance Win32_Service -Filter "Name='LanmanServer'" | Select-Object State,StartMode }
    power=Probe { (& powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 2>&1) -join "`n" }
    issues=$issues.ToArray()
    manual_checks=@('BIOS virtualization; WSL >=2.1.5; WSL2 backend; linux/amd64 engine','Subnet must not overlap LAN/VPN/Docker networks','AC sleep, power recovery, network recovery, Windows Update reboot and designated user login','Docker Desktop start at sign-in is not unattended boot recovery','Select authoritative data source separately; no database was migrated')
}
$json = $result | ConvertTo-Json -Depth 10
if ($Output) {
    if (Test-Path -LiteralPath $Output) { throw 'Output exists; preflight refuses overwrite' }
    $json | Set-Content -LiteralPath $Output -Encoding utf8
}
$json
