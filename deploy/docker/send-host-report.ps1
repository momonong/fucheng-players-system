<#
Windows PowerShell 5.1+: send an existing report, retaining the same operation
after a lost response. No token, exception body or raw HTTP response is printed.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ReportDirectory,
    [Parameter(Mandatory=$true)][string]$ConfigFile,
    [ValidateRange(3,60)][int]$TimeoutSeconds = 20
)
$ErrorActionPreference = 'Stop'
$utf8 = New-Object Text.UTF8Encoding($false)
function Write-NewJson([string]$Path, $Value) {
    $bytes = $utf8.GetBytes(($Value | ConvertTo-Json -Depth 8) + "`n")
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
}
function Write-Status([string]$State, $HttpStatus) {
    $path = Join-Path $directory 'upload-status.json'
    $temporary = $path + '.tmp-' + [Guid]::NewGuid().ToString('N')
    Write-NewJson $temporary ([ordered]@{report_id=$operation.report_id; state=$State;
        http_status=$HttpStatus; attempted_at=(Get-Date).ToUniversalTime().ToString('o')})
    if (Test-Path -LiteralPath $path) { [IO.File]::Replace($temporary, $path, [System.Management.Automation.Language.NullString]::Value) }
    else { [IO.File]::Move($temporary, $path) }
}
function Remaining-Milliseconds {
    $remaining = $TimeoutSeconds * 1000 - [int]$deliveryClock.ElapsedMilliseconds
    if ($remaining -le 0) { throw 'delivery deadline' }
    return $remaining
}
function Valid-Receipt($Value, $Operation) {
    $names = @($Value.PSObject.Properties.Name | Sort-Object)
    if (($names -join ',') -ne 'device_id,digest,received_at,report_id') { return $false }
    $when = [DateTimeOffset]::MinValue
    return ($Value.report_id -ceq $Operation.report_id -and
        $Value.device_id -ceq $Operation.device_id -and
        $Value.digest -cmatch '^[0-9a-f]{64}$' -and
        [DateTimeOffset]::TryParse([string]$Value.received_at, [ref]$when) -and
        $when.Year -ge 2020 -and $when.Year -le 2100)
}
try {
    $directory = [IO.Path]::GetFullPath($ReportDirectory)
    $configPath = [IO.Path]::GetFullPath($ConfigFile)
    $config = [IO.File]::ReadAllText($configPath, $utf8) | ConvertFrom-Json
    $endpoint = [string]$config.endpoint
    $target = $null
    if (![Uri]::TryCreate($endpoint, [UriKind]::Absolute, [ref]$target) -or
        $target.Scheme -ne 'https' -or $target.UserInfo -or $target.Query -or $target.Fragment -or
        $endpoint -cnotmatch '^https://[A-Za-z0-9.-]+(?::[0-9]+)?(?:/[A-Za-z0-9_-]+)*/api/deployment-reports$') {
        throw 'invalid endpoint'
    }
    if ([string]$config.device_id -cnotmatch '^[a-z0-9][a-z0-9_-]{0,63}$') { throw 'invalid device' }
    $reportPath = Join-Path $directory 'report.json'
    $reportFile = Get-Item -LiteralPath $reportPath
    if ($reportFile.Length -gt 262144 -or $reportFile.Length -lt 2) { throw 'report size' }
    $body = [IO.File]::ReadAllBytes($reportPath)
    $report = $utf8.GetString($body) | ConvertFrom-Json
    if ($report.schema_version -ne 1) { throw 'report schema' }
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $rawHash = ([BitConverter]::ToString($hasher.ComputeHash($body))).Replace('-','').ToLowerInvariant() }
    finally { $hasher.Dispose() }
    $operationPath = Join-Path $directory 'upload-operation.json'
    if (Test-Path -LiteralPath $operationPath) {
        $operation = [IO.File]::ReadAllText($operationPath, $utf8) | ConvertFrom-Json
        $operationGuid = [Guid]::Empty
        if ($operation.schema_version -ne 1 -or
            ![Guid]::TryParseExact([string]$operation.report_id, 'D', [ref]$operationGuid) -or
            $operation.endpoint -cne $endpoint -or $operation.device_id -cne [string]$config.device_id -or
            $operation.raw_report_sha256 -cne $rawHash) { throw 'operation mismatch' }
    } else {
        $operation = [ordered]@{schema_version=1; report_id=[Guid]::NewGuid().ToString('D');
            endpoint=$endpoint; device_id=[string]$config.device_id; raw_report_sha256=$rawHash}
        Write-NewJson $operationPath $operation
        # Read the persisted operation before opening the network connection.
        $operation = [IO.File]::ReadAllText($operationPath, $utf8) | ConvertFrom-Json
    }
    $receiptPath = Join-Path $directory 'upload-receipt.json'
    if (Test-Path -LiteralPath $receiptPath) {
        $saved = [IO.File]::ReadAllText($receiptPath, $utf8) | ConvertFrom-Json
        if (!(Valid-Receipt $saved $operation)) { throw 'receipt mismatch' }
        Write-Output "報告先前已接收，沿用原收據。report_id=$($operation.report_id)"
        exit 0
    }
    $tokenPath = [string]$config.token_file
    if (![IO.Path]::IsPathRooted($tokenPath)) { $tokenPath = Join-Path ([IO.Path]::GetDirectoryName($configPath)) $tokenPath }
    $tokenInfo = Get-Item -LiteralPath $tokenPath
    if ($tokenInfo.Length -gt 256 -or $tokenInfo.PSIsContainer) { throw 'token file' }
    $token = [IO.File]::ReadAllText($tokenPath, $utf8).Trim()
    if ($token -cnotmatch '^(?:[0-9a-f]{2}){32,64}$') { throw 'invalid token' }
} catch {
    Write-Output '未開始上傳：請核對私密設定、原始報告及 operation；沒有覆寫原檔。'
    exit 2
}

$request = $null
$response = $null
$status = $null
$outcome = 'unknown'
$previousTls = [Net.ServicePointManager]::SecurityProtocol
$deliveryClock = [Diagnostics.Stopwatch]::StartNew()
try {
    Write-Status 'unknown' $null
    [Net.ServicePointManager]::SecurityProtocol = $previousTls -bor [Net.SecurityProtocolType]::Tls12
    $request = [Net.HttpWebRequest]::Create($endpoint + '/' + $operation.report_id)
    $request.Method = 'POST'
    $request.AllowAutoRedirect = $false
    $request.KeepAlive = $false
    $request.Timeout = Remaining-Milliseconds
    $request.ReadWriteTimeout = $TimeoutSeconds * 1000
    $request.MaximumResponseHeadersLength = 16
    $request.ContentType = 'application/json; charset=utf-8'
    $request.Accept = 'application/json'
    $request.ContentLength = $body.Length
    $request.Headers['Origin'] = $target.GetLeftPart([UriPartial]::Authority)
    $request.Headers['X-Fucheng-Report-Token'] = $token
    $pending = $request.BeginGetRequestStream($null, $null)
    $waiting = $pending.AsyncWaitHandle
    try {
        if (!$waiting.WaitOne((Remaining-Milliseconds))) { throw 'delivery deadline' }
        $stream = $request.EndGetRequestStream($pending)
    } finally { $waiting.Close() }
    try {
        $pending = $stream.BeginWrite($body, 0, $body.Length, $null, $null)
        $waiting = $pending.AsyncWaitHandle
        try {
            if (!$waiting.WaitOne((Remaining-Milliseconds))) { throw 'delivery deadline' }
            $stream.EndWrite($pending)
        } finally { $waiting.Close() }
    }
    finally { $stream.Dispose() }
    try {
        $pending = $request.BeginGetResponse($null, $null)
        $waiting = $pending.AsyncWaitHandle
        try {
            if (!$waiting.WaitOne((Remaining-Milliseconds))) { throw 'delivery deadline' }
            $response = $request.EndGetResponse($pending)
        } finally { $waiting.Close() }
    }
    catch [Net.WebException] {
        if ($_.Exception.Response) { $response = $_.Exception.Response } else { throw }
    }
    $status = [int]$response.StatusCode
    if ($status -eq 200) {
        $inputStream = $response.GetResponseStream()
        $buffer = New-Object byte[] 4097
        $received = 0
        try {
            while ($received -lt $buffer.Length) {
                $pending = $inputStream.BeginRead($buffer, $received, $buffer.Length - $received, $null, $null)
                $waiting = $pending.AsyncWaitHandle
                try {
                    if (!$waiting.WaitOne((Remaining-Milliseconds))) { throw 'delivery deadline' }
                    $read = $inputStream.EndRead($pending)
                } finally { $waiting.Close() }
                if ($read -eq 0) { break }
                $received += $read
            }
        } finally { $inputStream.Dispose() }
        if ($received -gt 4096) { throw 'receipt exceeds limit' }
        $receipt = $utf8.GetString($buffer, 0, $received) | ConvertFrom-Json
        if (!(Valid-Receipt $receipt $operation)) { throw 'invalid receipt' }
        Write-NewJson $receiptPath $receipt
        $outcome = 'received'
    } else { $outcome = 'rejected' }
} catch {
    # A timeout/disconnect/bad receipt can occur after a successful server commit.
    # Keep the exact operation and body; never silently allocate a new report_id.
    $outcome = 'unknown'
} finally {
    if ($response) { try { $response.Dispose() } catch {} }
    if ($request) { try { $request.Abort() } catch {} }
    $token = $null
    [Net.ServicePointManager]::SecurityProtocol = $previousTls
}
try { Write-Status $outcome $status }
catch { Write-Output '無法保存本機狀態，請保留原 operation 與收據交管理者核對。' }
if ($outcome -eq 'received') {
    Write-Output "報告已接收。report_id=$($operation.report_id); receipt=$receiptPath"
    Write-Output '收據只證明已保存，不表示檢查通過或准予部署。'
    exit 0
}
if ($outcome -eq 'rejected') {
    Write-Output "報告未被接受。HTTP=$status。本機報告與原 operation 保留，未跟隨任何重新導向。"
    Write-Output '409 請停止並交管理者核對；429／507 請保留原檔，稍候或處理容量後以同一 ID 重試。'
    exit 3
}
Write-Output '傳送結果未知（UNKNOWN）。本機報告與 operation 已保留，請用原報告資料夾及設定重試，不要建立新 ID。'
exit 4
