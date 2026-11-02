<# One-shot read-only Windows host check; credentials travel only in private files. #>
[CmdletBinding()]
param(
    [switch]$NewCheck,
    [switch]$PrepareOnly,
    [ValidateRange(3,240)][int]$DeadlineSeconds = 240
)
$ErrorActionPreference = 'Stop'
$clock = [Diagnostics.Stopwatch]::StartNew()
$utf8 = New-Object Text.UTF8Encoding($false)
$sourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$fixedImage = 'momonong/fucheng-players-system@sha256:0e5a297b0d16876fa56e1b9bed0470c3b8632d55ded6b23ffc5c18315f39e6e2'
$workspace = $null
$lock = $null
$failure = '無法準備健檢工作區；請確認以球館平常使用者執行，且本機應用程式資料夾可寫。'
function Assert-RegularPath([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'linked tool path' }
    }
}
function Restrict-ToolDirectory([string]$Path) {
    # Called only for this tool's newly-created or marker-owned directory.
    if ($env:OS -eq 'Windows_NT') {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
        $acl = New-Object Security.AccessControl.DirectorySecurity
        $acl.SetOwner($identity)
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($sid in @($identity, (New-Object Security.Principal.SecurityIdentifier('S-1-5-18')), (New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))) {
            $rule = New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
            [void]$acl.AddAccessRule($rule)
        }
        Set-Acl -LiteralPath $Path -AclObject $acl
    } else {
        # Portable PowerShell test harness only; never claimed as Windows ACL evidence.
        [IO.File]::SetUnixFileMode($Path, [IO.UnixFileMode]::UserRead -bor [IO.UnixFileMode]::UserWrite -bor [IO.UnixFileMode]::UserExecute)
    }
}
function Restrict-ToolPrivateFile([string]$Path) {
    if ($env:OS -eq 'Windows_NT') {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
        $acl = New-Object Security.AccessControl.FileSecurity
        $acl.SetOwner($identity)
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($sid in @($identity, (New-Object Security.Principal.SecurityIdentifier('S-1-5-18')), (New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))) {
            [void]$acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'Allow')))
        }
        Set-Acl -LiteralPath $Path -AclObject $acl
    } else {
        [IO.File]::SetUnixFileMode($Path, [IO.UnixFileMode]::UserRead -bor [IO.UnixFileMode]::UserWrite)
    }
}
function Save-Json([string]$Path, $Value) {
    $temporary = $Path + '.tmp-' + [Guid]::NewGuid().ToString('N')
    [IO.File]::WriteAllText($temporary, (($Value | ConvertTo-Json -Depth 5) + "`n"), $utf8)
    if (Test-Path -LiteralPath $Path) { [IO.File]::Replace($temporary, $Path, [System.Management.Automation.Language.NullString]::Value) }
    else { [IO.File]::Move($temporary, $Path) }
}
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
function Invoke-ToolChild([string]$Script, [hashtable]$Options, [string]$Label) {
    $remaining = $DeadlineSeconds * 1000 - $clock.ElapsedMilliseconds
    if ($remaining -le 0) { return @{timed_out=$true; exit_code=$null} }
    # EncodedCommand contains only reviewed script/options/paths, never token bytes.
    $argumentsJson = $Options | ConvertTo-Json -Compress
    $escapedScript = $Script.Replace("'", "''")
    $escapedOptions = $argumentsJson.Replace("'", "''")
    $command = "`$ErrorActionPreference='Stop'; try { `$v='$escapedOptions' | ConvertFrom-Json; `$a=@{}; foreach (`$p in `$v.PSObject.Properties) { `$a[`$p.Name]=`$p.Value }; & '$escapedScript' @a; if (`$null -ne `$LASTEXITCODE) { exit `$LASTEXITCODE }; exit 0 } catch { exit 2 }"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = (Get-Process -Id $PID).Path
    $psi.Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $encoded"
    $psi.WorkingDirectory = $workspace
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $psi
    try {
        [void]$process.Start()
        # Drain without forwarding raw exceptions, HTTP bodies or private file content.
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $nextProgress = $clock.ElapsedMilliseconds + 10000
        while (!$process.WaitForExit(200)) {
            if ($clock.ElapsedMilliseconds -ge $DeadlineSeconds * 1000) {
                $cleanup = Stop-OwnedProcessTree $process
                return @{timed_out=$true; exit_code=$null; cleanup_confirmed=$cleanup}
            }
            if ($clock.ElapsedMilliseconds -ge $nextProgress) {
                Write-Host ("仍在{0}，已執行 {1} 秒；總上限 {2} 秒。" -f $Label, [int]$clock.Elapsed.TotalSeconds, $DeadlineSeconds)
                $nextProgress = $clock.ElapsedMilliseconds + 10000
            }
        }
        # Never block on Result when inherited pipes have not closed.
        return @{timed_out=$false; exit_code=$process.ExitCode}
    } catch { return @{timed_out=$false; exit_code=2} }
    finally { $process.Dispose() }
}
try {
    $local = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
    if (!$local -or !(Test-Path -LiteralPath $local -PathType Container)) {
        # Native API can return a not-yet-created per-user app data directory.
        if (!$local -or ![IO.Path]::IsPathRooted($local)) { throw 'local application data unavailable' }
        [void][IO.Directory]::CreateDirectory($local)
    }
    Assert-RegularPath $local
    $workspace = Join-Path $local 'FuchengClubHostCheck'
    Assert-RegularPath $workspace
    $marker = Join-Path $workspace '.fucheng-host-check-owned'
    if (Test-Path -LiteralPath $workspace) {
        Assert-RegularPath $marker
        if (!(Test-Path -LiteralPath $marker -PathType Leaf) -or [IO.File]::ReadAllText($marker) -cne 'fucheng-host-check-v1') { throw 'existing directory not owned by tool' }
        # Refuse links inside our workspace before copying or changing ACLs.
        foreach ($item in @(Get-ChildItem -LiteralPath $workspace -Force -Recurse)) { Assert-RegularPath $item.FullName }
    } else {
        [void][IO.Directory]::CreateDirectory($workspace)
        Restrict-ToolDirectory $workspace
        [IO.File]::WriteAllText($marker, 'fucheng-host-check-v1', $utf8)
    }
    Restrict-ToolDirectory $workspace
    $failure = '另一個健檢仍在執行，或工作區被鎖定。請等原視窗完成，再重跑同一入口。'
    $lock = [IO.File]::Open((Join-Path $workspace 'runner.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    Write-Output '開始球館主機唯讀健檢；不會重開機、安裝軟體或修改服務／電源／防火牆。'
    Write-Output "本機工作區：$workspace"
    $failure = '工具或私密設定檔缺失／格式不符。請管理者重新傳送完整 ready 資料夾；不要貼出 token。'
    foreach ($relative in @('deploy','deploy/docker','private','data')) { [void][IO.Directory]::CreateDirectory((Join-Path $workspace $relative)) }
    Restrict-ToolDirectory (Join-Path $workspace 'private')
    foreach ($name in @('host-preflight.ps1','send-host-report.ps1')) {
        $source = Join-Path $PSScriptRoot $name
        Assert-RegularPath $source
        $destination = Join-Path $workspace ('deploy/docker/' + $name)
        if ([IO.Path]::GetFullPath($source) -cne [IO.Path]::GetFullPath($destination)) { [IO.File]::Copy($source, $destination, $true) }
    }
    $sourceConfig = Join-Path $sourceRoot 'private/club-report.json'
    $configFile = Join-Path $workspace 'private/club-report.json'
    $hasConfig = Test-Path -LiteralPath $sourceConfig -PathType Leaf
    if ($hasConfig) {
        Assert-RegularPath (Join-Path $sourceRoot 'private')
        Assert-RegularPath $sourceConfig
        if ((Get-Item -LiteralPath $sourceConfig).Length -gt 8192) { throw 'configuration too large' }
        $configuration = [IO.File]::ReadAllText($sourceConfig, $utf8) | ConvertFrom-Json
        $tokenName = [string]$configuration.token_file
        if ($tokenName -notmatch '^[A-Za-z0-9_.-]{1,100}$' -or $tokenName -in @('.','..')) { throw 'token must be a private filename' }
        $tokenSource = Join-Path (Join-Path $sourceRoot 'private') $tokenName
        Assert-RegularPath $tokenSource
        $tokenDestination = Join-Path $workspace 'private/report-upload-token.txt'
        $effectiveTokenName = 'report-upload-token.txt'
        if (Test-Path -LiteralPath $tokenSource -PathType Leaf) {
            if ((Get-Item -LiteralPath $tokenSource).Length -gt 1024) { throw 'token file too large' }
            if ([IO.Path]::GetFullPath($tokenSource) -cne [IO.Path]::GetFullPath($tokenDestination)) { [IO.File]::Copy($tokenSource, $tokenDestination, $true) }
        } else {
            # Explicit source settings never silently adopt an older credential.
            # Persist a fresh absent reference, so omitting source settings later
            # cannot reactivate the preserved old token. No credential is deleted.
            $effectiveTokenName = 'credential-unavailable-' + [Guid]::NewGuid().ToString('N') + '.txt'
        }
        if (Test-Path -LiteralPath $tokenDestination -PathType Leaf) { Restrict-ToolPrivateFile $tokenDestination }
        Save-Json $configFile ([ordered]@{endpoint=[string]$configuration.endpoint;device_id=[string]$configuration.device_id;token_file=$effectiveTokenName})
        Restrict-ToolPrivateFile $configFile
    }
    $activePath = Join-Path $workspace 'active-report.json'
    $directory = $null
    if (Test-Path -LiteralPath $activePath) {
        $active = [IO.File]::ReadAllText($activePath, $utf8) | ConvertFrom-Json
        if ([string]$active.directory -cnotmatch '^data/host-[0-9a-f]{32}$') { throw 'invalid active report' }
        $directory = Join-Path $workspace $active.directory
        if ($NewCheck) {
            if (!(Test-Path -LiteralPath (Join-Path $directory 'upload-receipt.json'))) {
                Write-Output '前次報告尚無已接收收據；本次只重送原檔，不建立新 UUID。'
            } else {
                # Sender validates report hash, operation binding and strict receipt.
                if (!(Test-Path -LiteralPath $configFile -PathType Leaf)) { throw 'receipt requires original configuration' }
                Write-Output '先核對前次原始報告、operation 與收據，再建立新檢查…'
                $cached = Invoke-ToolChild (Join-Path $workspace 'deploy/docker/send-host-report.ps1') @{ReportDirectory=$directory; ConfigFile=$configFile; TimeoutSeconds=20} '核對原收據'
                if ($cached.timed_out) {
                    Write-Output '原收據核對已達時限；保留前份報告，沒有建立新檢查。請重跑同一入口。'
                    exit 4
                }
                if ($cached.exit_code -ne 0) {
                    Write-Output '前次收據／operation／原始報告無法通過綁定核對；已保留前份，請管理者核對，沒有建立新檢查。'
                    exit 2
                }
                $directory = $null
            }
        }
    }
    if (!$directory) {
        if (!$hasConfig -and (Test-Path -LiteralPath $configFile -PathType Leaf)) {
            # A stored credential can resume its existing report, but cannot
            # authorize a newly requested check without the explicit ready config.
            $storedConfiguration = [IO.File]::ReadAllText($configFile, $utf8) | ConvertFrom-Json
            Save-Json $configFile ([ordered]@{endpoint=[string]$storedConfiguration.endpoint;device_id=[string]$storedConfiguration.device_id;token_file=('credential-unavailable-' + [Guid]::NewGuid().ToString('N') + '.txt')})
            Restrict-ToolPrivateFile $configFile
        }
        $relativeReport = 'data/host-' + [Guid]::NewGuid().ToString('N')
        $directory = Join-Path $workspace $relativeReport
        Save-Json $activePath ([ordered]@{directory=$relativeReport})
    }
    $failure = '健檢未能完成。請保留工作區，核對 Docker Desktop 是否可用；再次執行同一入口，勿刪除既有報告或 operation。'
    if (!(Test-Path -LiteralPath (Join-Path $directory 'report.json'))) {
        if (Test-Path -LiteralPath $directory) { throw 'incomplete report directory preserved' }
        Write-Output '正在檢查 Windows、Docker 與指定試用容器（最長約四分鐘）…'
        $preflight = Invoke-ToolChild (Join-Path $workspace 'deploy/docker/host-preflight.ps1') @{
            OutputDir=$directory; InstallPath=$workspace; ContainerName='fucheng-check-v120';TestPort=8052;
            ImageRef=$fixedImage; TimeoutSeconds=5; ProbeNetwork=$true
        } '健檢'
        if ($preflight.timed_out) {
            Write-Output '健檢已達總時限，已要求停止本工具啟動的檢查程序樹；沒有重啟 Docker 或 Windows。'
            if (!$preflight.cleanup_confirmed) { Write-Output '無法確認本工具所有衍生查詢均已結束，請保留工作區交管理者核對；未按名稱停止其他程序。' }
            exit 5
        }
        if ($preflight.exit_code -ne 0) { throw 'preflight failed' }
    } else { Write-Output '沿用前次報告；保留原始檔及原 UUID，不重新檢查。' }
    if (!(Test-Path -LiteralPath (Join-Path $directory 'report.md'))) { throw 'incomplete report' }
    Write-Output "本機報告：$directory"
    $report = [IO.File]::ReadAllText((Join-Path $directory 'report.json'), $utf8) | ConvertFrom-Json
    Write-Output ("檢查結果：PASS {0}／WARN {1}／FAIL {2}／NOT_TESTED {3}；有 FAIL 仍會回傳。" -f $report.summary.PASS,$report.summary.WARN,$report.summary.FAIL,$report.summary.NOT_TESTED)
    if (!(Test-Path -LiteralPath $configFile -PathType Leaf)) {
        Write-Output '報告已保存，但缺少私密回傳設定，尚未傳送。請管理者補齊 ready 資料夾後重跑同一入口。'
        exit 2
    }
    if ($PrepareOnly) {
        $prepared = Invoke-ToolChild (Join-Path $workspace 'deploy/docker/send-host-report.ps1') @{ReportDirectory=$directory; ConfigFile=$configFile; PrepareOnly=$true; TimeoutSeconds=20} '準備原 operation'
        if ($prepared.timed_out) { exit 4 }
        if ($prepared.exit_code -ne 0) { exit $prepared.exit_code }
        Write-Output '原報告與 UUID 已保存；本階段沒有傳送報告。'
        exit 0
    }
    Write-Output '正在回傳或核對原收據；接收站只用來收報告，球館正式網域尚未設定。'
    $delivery = Invoke-ToolChild (Join-Path $workspace 'deploy/docker/send-host-report.ps1') @{ReportDirectory=$directory; ConfigFile=$configFile; TimeoutSeconds=20} '回傳／核對收據'
    if ($delivery.timed_out) {
        Write-Output '回傳已達總時限，結果未知。原報告與 operation 已保留；請重跑同一入口重送，勿建立新 ID。'
        if (!$delivery.cleanup_confirmed) { Write-Output '無法確認本工具所有衍生查詢均已結束，請交管理者核對。' }
        exit 4
    }
    if ($delivery.exit_code -eq 0) {
        $receiptFile = Join-Path $directory 'upload-receipt.json'
        $receipt = [IO.File]::ReadAllText($receiptFile, $utf8) | ConvertFrom-Json
        Write-Output "報告已接收（或先前已接收），report_id=$($receipt.report_id)"
        Write-Output "收據：$receiptFile"
        Write-Output '收據只證明報告已保存，不表示檢查通過、正式部署或冷開機驗收完成。'
        Write-Output '要明確重新檢查，請使用「NEW-CHECK.cmd」；一般重跑會沿用收據。'
        exit 0
    }
    if ($delivery.exit_code -eq 2) {
        Write-Output '報告已保存，尚未完成回傳；請管理者核對私密 token／設定與 operation，勿貼出 token。補齊後重跑同一入口。'
        exit 2
    }
    if ($delivery.exit_code -eq 3) {
        Write-Output '接收站未接受報告。請保留原報告與 operation 交管理者核對；不要刪檔或重新產生 UUID。'
        exit 3
    }
    Write-Output '回傳結果未知；原報告與 operation 已保留。請重跑同一入口，使用相同 UUID 重送。'
    exit 4
} catch {
    # Never forward raw exception text, command output, config or response bodies.
    Write-Output $failure
    if ($workspace) { Write-Output "保留位置：$workspace" }
    exit 2
} finally {
    if ($lock) { $lock.Dispose() }
}
