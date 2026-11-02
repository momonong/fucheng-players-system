# Interactive child: password/session remain in memory, only the one-report token is persisted.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$ReportDirectory,[Parameter(Mandatory=$true)][string]$ConfigFile)
$ErrorActionPreference = 'Stop'
$utf8 = New-Object Text.UTF8Encoding($false)
. (Join-Path $PSScriptRoot 'club-host-network.ps1')
$cookies = New-Object Net.CookieContainer
$csrf = $null; $api = $null; $credential = $null; $password = $null; $loginBytes = $null
$username = $null; $securePassword = $null; $stage = 'config'
try {
    $configuration = [IO.File]::ReadAllText($ConfigFile,$utf8) | ConvertFrom-Json
    $endpoint = [string]$configuration.endpoint
    if ($endpoint -cnotmatch '^https://momonong\.me/fucheng/api/deployment-reports$') { throw 'unexpected receiver' }
    $api = $endpoint.Substring(0,$endpoint.Length - '/deployment-reports'.Length)
    $stage = 'operation'
    $operation = [IO.File]::ReadAllText((Join-Path $ReportDirectory 'upload-operation.json'),$utf8) | ConvertFrom-Json
    if ($operation.endpoint -cne $endpoint -or $operation.device_id -cne [string]$configuration.device_id -or [string]$operation.report_id -cnotmatch '^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$') { throw 'operation mismatch' }
    $stage = 'username'
    $username = Read-Host -Prompt 'momonong.me/fucheng 接收站管理員帳號'
    if ([string]::IsNullOrWhiteSpace($username)) { throw 'EMPTY_USERNAME' }
    $stage = 'password'
    $securePassword = Read-Host -AsSecureString -Prompt '接收站管理員密碼（隱藏輸入）'
    if (!$securePassword -or $securePassword.Length -eq 0) { throw 'EMPTY_PASSWORD' }
    $credential = New-Object Management.Automation.PSCredential($username.Trim(),$securePassword)
    $stage = 'login'
    $password = $credential.GetNetworkCredential().Password
    $loginBytes = $utf8.GetBytes(([ordered]@{username=$credential.UserName;password=$password} | ConvertTo-Json -Compress))
    $login = $utf8.GetString((Invoke-ToolHttp ($api+'/auth/login') 'POST' $loginBytes $cookies '' 16384 20)) | ConvertFrom-Json
    $csrf = [string]$login.csrf_token
    if ($login.must_change_password -or $csrf -cnotmatch '^[A-Za-z0-9_-]{20,100}$') { throw 'password change required or invalid login' }
    $body = $utf8.GetBytes((@{report_id=[string]$operation.report_id} | ConvertTo-Json -Compress))
    $stage = 'capability'
    $value = $utf8.GetString((Invoke-ToolHttp ($api+'/admin/deployment-report-capability') 'POST' $body $cookies $csrf 16384 20)) | ConvertFrom-Json
    if ($value.report_id -cne $operation.report_id -or $value.device_id -cne $operation.device_id -or [string]$value.token -cnotmatch '^fcr1\.[A-Za-z0-9_-]+\.[0-9a-f]{64}$' -or ([string]$value.token).Length -gt 1024) { throw 'invalid capability' }
    $stage = 'token_write'
    $tokenPath = Join-Path ([IO.Path]::GetDirectoryName($ConfigFile)) 'report-upload-token.txt'
    $stream = [IO.File]::Open($tokenPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try { $bytes=$utf8.GetBytes([string]$value.token);$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true) } finally {$stream.Dispose()}
    Write-Host '已取得此份報告專用的一小時回傳權限。'
    $exitCode = 0
} catch {
    $safeStage = if ($stage -cin @('config','operation','username','password','login','capability','token_write')) { $stage } else { 'prepare' }
    Write-Host ('回傳準備失敗：stage={0}; type={1}。原報告與 UUID 保留；不要貼出密碼或 token。' -f $safeStage,$_.Exception.GetType().FullName)
    $exitCode = 2
} finally {
    if ($api -and $csrf) { try { $null = Invoke-ToolHttp ($api+'/auth/logout') 'POST' $utf8.GetBytes('{}') $cookies $csrf 1024 10 } catch { Write-Host '接收站登出尚未確認；session 僅在此程序記憶體，請管理者在接收站核對。' } }
    if ($loginBytes) { [Array]::Clear($loginBytes,0,$loginBytes.Length) }
    $password=$null;$credential=$null;$securePassword=$null;$username=$null;$csrf=$null;$cookies=$null;$value=$null
}
exit $exitCode
