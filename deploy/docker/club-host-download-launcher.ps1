& {
    $ErrorActionPreference = 'Stop'
    $client = $null; $response = $null
    $tls = [Net.ServicePointManager]::SecurityProtocol
    try {
        Add-Type -AssemblyName System.Net.Http
        [Net.ServicePointManager]::SecurityProtocol = $tls -bor [Net.SecurityProtocolType]::Tls12
        $handler = New-Object Net.Http.HttpClientHandler
        $handler.AllowAutoRedirect = $false
        $client = New-Object Net.Http.HttpClient($handler)
        $client.Timeout = [TimeSpan]::FromSeconds(30)
        $client.MaxResponseContentBufferSize = 131072
        $response = $client.GetAsync('@@BOOTSTRAP_URL@@').GetAwaiter().GetResult()
        if ([int]$response.StatusCode -ne 200) { throw 'download refused' }
        $bytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $hash = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant() } finally { $sha.Dispose() }
        if ($hash -cne '@@BOOTSTRAP_SHA256@@') { throw 'SHA256 mismatch' }
        & ([scriptblock]::Create([Text.Encoding]::UTF8.GetString($bytes).TrimStart([char]0xFEFF)))
    } catch { Write-Host '尚未完成：下載被拒絕、逾時或 SHA256 不符。請重貼完整原指令；不要貼出密碼或 token。' }
    finally {
        if ($response) { $response.Dispose() }; if ($client) { $client.Dispose() }
        [Net.ServicePointManager]::SecurityProtocol = $tls
    }
}
