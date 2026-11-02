# Builder embeds club-host-network.ps1 before this body. No secrets in this artifact.
$ErrorActionPreference = 'Stop'
$endpoint = '@@ENDPOINT@@'
$deviceId = '@@DEVICE_ID@@'
$zipHash = '@@ZIP_SHA256@@'
$zipUrl = '@@ZIP_URL@@'
$utf8 = New-Object Text.UTF8Encoding($false)
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
function Expand-VerifiedToolZip([string]$Archive,[string]$Destination) {
    Add-Type -AssemblyName System.IO.Compression
    if (Test-Path -LiteralPath $Destination) { throw 'destination exists' }
    $file = [IO.File]::OpenRead($Archive)
    $zip = New-Object IO.Compression.ZipArchive($file,[IO.Compression.ZipArchiveMode]::Read,$false)
    try {
        $entries = @{}; $bytes = @{}; $total = 0
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName
            if ($name -cnotmatch '^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$' -or @($name.Split('/') | Where-Object { $_ -in @('.','..') }).Count -gt 0 -or $entries.ContainsKey($name)) { throw 'unsafe ZIP entry' }
            $mode = ($entry.ExternalAttributes -shr 16) -band 61440
            if ($mode -notin @(0,32768) -or $entry.Length -gt 2097152 -or $entry.Length -lt 0) { throw 'ZIP entry mode or size' }
            $total += $entry.Length
            if ($total -gt 2097152 -or $entries.Count -ge 32) { throw 'ZIP size limit' }
            $entries[$name] = $entry
            $stream = $entry.Open(); $memory = New-Object IO.MemoryStream
            try { $stream.CopyTo($memory); if ($memory.Length -ne $entry.Length) { throw 'ZIP entry size mismatch' }; $bytes[$name] = $memory.ToArray() }
            finally { $memory.Dispose(); $stream.Dispose() }
        }
        if (!$entries.ContainsKey('manifest.json')) { throw 'missing manifest' }
        $manifest = [Text.Encoding]::UTF8.GetString($bytes['manifest.json']) | ConvertFrom-Json
        if ($manifest.schema_version -ne 1 -or $manifest.kind -cne 'club-host-one-shot-kit' -or $manifest.contains_credentials -ne $false) { throw 'manifest invalid' }
        if (@($manifest.files.PSObject.Properties).Count -ne $entries.Count - 1) { throw 'manifest entries mismatch' }
        foreach ($property in $manifest.files.PSObject.Properties) {
            if ($property.Name -ceq 'manifest.json' -or !$entries.ContainsKey($property.Name) -or [string]$property.Value -cnotmatch '^[0-9a-f]{64}$') { throw 'manifest entry invalid' }
            $hash = [Security.Cryptography.SHA256]::Create()
            try { $actual = ([BitConverter]::ToString($hash.ComputeHash($bytes[$property.Name]))).Replace('-','').ToLowerInvariant() } finally { $hash.Dispose() }
            if ($actual -cne [string]$property.Value) { throw 'manifest hash mismatch' }
        }
        # All paths, types, counts and body hashes are checked before writing anything.
        [void][IO.Directory]::CreateDirectory($Destination)
        foreach ($name in $bytes.Keys) {
            $path = Join-Path $Destination $name
            [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path))
            $stream = [IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
            try { $stream.Write($bytes[$name],0,$bytes[$name].Length) } finally { $stream.Dispose() }
        }
    } finally { $zip.Dispose(); $file.Dispose() }
}
function Invoke-BootstrapChild([string]$Script,[hashtable]$Options,[int]$TimeoutSeconds,[switch]$Interactive) {
    # Only paths/switches are in arguments. Bypass applies solely to this short-lived process.
    $json = ($Options | ConvertTo-Json -Compress).Replace("'","''")
    $command = "`$ErrorActionPreference='Stop'; try { `$v='"+$json+"' | ConvertFrom-Json; `$a=@{}; foreach (`$p in `$v.PSObject.Properties) { `$a[`$p.Name]=`$p.Value }; & '"+$Script.Replace("'","''")+"' @a; exit `$LASTEXITCODE } catch { exit 2 }"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = (Get-Process -Id $PID).Path
    $interactiveFlag = '-NonInteractive '
    if ($Interactive) { $interactiveFlag = '' }
    $psi.Arguments = '-NoProfile '+$interactiveFlag+'-ExecutionPolicy Bypass -EncodedCommand '+$encoded
    $psi.UseShellExecute = $false
    $process = New-Object Diagnostics.Process; $process.StartInfo = $psi
    try {
        [void]$process.Start()
        if (!$process.WaitForExit($TimeoutSeconds*1000)) {
            if ($env:OS -eq 'Windows_NT') {
                $kill = Start-Process -FilePath (Join-Path ([Environment]::SystemDirectory) 'taskkill.exe') -ArgumentList @('/PID',[string]$process.Id,'/T','/F') -NoNewWindow -PassThru -RedirectStandardOutput (Join-Path $downloadRoot 'child-cleanup.out') -RedirectStandardError (Join-Path $downloadRoot 'child-cleanup.err')
                try { if (!$kill.WaitForExit(2000)) { $kill.Kill() }; if ($kill.ExitCode -ne 0) { Write-Host '無法確認本工具子程序已完全停止；請保留現場核對。' } } finally { $kill.Dispose() }
            } else { $process.Kill($true) }
            throw 'tool child timeout'
        }
        return [int]$process.ExitCode
    } finally { $process.Dispose() }
}
function Invoke-CredentialHelper([string]$Script,[string]$ReportDirectory,[string]$ConfigFile) {
    $result = Invoke-BootstrapChild $Script @{ReportDirectory=$ReportDirectory;ConfigFile=$ConfigFile} 150 -Interactive
    if ($result -ne 0) { throw 'credential acquisition failed' }
}
function Invoke-RunnerHelper([string]$Script,[switch]$PrepareOnly) {
    $options = @{}
    if ($PrepareOnly) { $options.PrepareOnly = $true }
    return Invoke-BootstrapChild $Script $options 250
}
$lock = $null; $tokenFile = $null
try {
    $local = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
    if (!$local -or ![IO.Path]::IsPathRooted($local)) { throw 'app data unavailable' }
    Assert-NoToolLink $local
    $downloadRoot = Join-Path $local 'FuchengClubDownloads'
    Assert-NoToolLink $downloadRoot
    $marker = Join-Path $downloadRoot 'owner.txt'
    if (Test-Path -LiteralPath $downloadRoot) {
        Assert-NoToolLink $marker
        if (!(Test-Path -LiteralPath $marker -PathType Leaf) -or [IO.File]::ReadAllText($marker) -cne 'fucheng-club-download-v1') { throw 'unowned download directory' }
        if ($env:OS -eq 'Windows_NT') {
            $owner = (Get-Acl -LiteralPath $downloadRoot).GetOwner([Security.Principal.SecurityIdentifier])
            if ($owner -ne [Security.Principal.WindowsIdentity]::GetCurrent().User) { throw 'wrong directory owner' }
        }
        foreach ($item in @(Get-ChildItem -LiteralPath $downloadRoot -Force -Recurse)) { Assert-NoToolLink $item.FullName }
    } else {
        [void][IO.Directory]::CreateDirectory($downloadRoot); Set-ToolPrivateDirectory $downloadRoot
        [IO.File]::WriteAllText($marker,'fucheng-club-download-v1',$utf8)
    }
    Set-ToolPrivateDirectory $downloadRoot
    $lock = [IO.File]::Open((Join-Path $downloadRoot 'download.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    Write-Host '下載並核對固定 SHA256 工具；接下來只做唯讀健檢，不會重開機。'
    $zipBytes = Invoke-ToolHttp $zipUrl
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $actual = ([BitConverter]::ToString($hasher.ComputeHash($zipBytes))).Replace('-','').ToLowerInvariant() } finally { $hasher.Dispose() }
    if ($actual -cne $zipHash) { throw 'download SHA256 mismatch' }
    $run = Join-Path $downloadRoot ('run-'+[Guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($run)
    $archive = Join-Path $run 'tools.zip'; [IO.File]::WriteAllBytes($archive,$zipBytes)
    $kit = Join-Path $run 'kit'; Expand-VerifiedToolZip $archive $kit
    $config = Join-Path $kit 'private/club-report.json'
    $configuration = [ordered]@{endpoint=$endpoint;device_id=$deviceId;token_file='report-upload-token.txt'}
    [IO.File]::WriteAllText($config,($configuration | ConvertTo-Json -Compress),$utf8)
    $runner = Join-Path $kit 'deploy/docker/club-host-one-shot.ps1'
    $prepared = Invoke-RunnerHelper $runner -PrepareOnly
    if ($prepared -ne 0) { throw 'report preparation failed' }
    $workspace = Join-Path $local 'FuchengClubHostCheck'
    $active = [IO.File]::ReadAllText((Join-Path $workspace 'active-report.json')) | ConvertFrom-Json
    if ([string]$active.directory -cnotmatch '^data/host-[0-9a-f]{32}$') { throw 'invalid active report' }
    $reportDirectory = Join-Path $workspace $active.directory
    if (!(Test-Path -LiteralPath (Join-Path $reportDirectory 'upload-receipt.json'))) {
        Write-Host '請在本終端輸入 momonong.me/fucheng 接收站既有管理員；密碼會隱藏。不是球館本機帳號。登入最多等待 150 秒。'
        $tokenFile = Join-Path $kit 'private/report-upload-token.txt'
        Invoke-CredentialHelper (Join-Path $kit 'deploy/docker/club-host-credential.ps1') $reportDirectory $config
    }
    $result = Invoke-RunnerHelper $runner
    if ($result -ne 0) { Write-Host '原報告及 UUID 已保留；重新貼同一段指令即可繼續。' }
    $global:LASTEXITCODE = $result
    return
} catch {
    Write-Host '下載／登入／健檢未完成。未執行未核對的工具；原報告與 UUID 保留。請重貼同一段指令；不要貼出密碼或 token。'
    $global:LASTEXITCODE = 2
    return
} finally {
    if ($tokenFile -and (Test-Path -LiteralPath $tokenFile -PathType Leaf)) { [IO.File]::Delete($tokenFile) }
    if ($lock) { $lock.Dispose() }
}
