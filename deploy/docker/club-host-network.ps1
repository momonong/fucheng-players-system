# Shared bounded TLS transport. Never print request/response bodies or exceptions.
function Invoke-ToolHttp([string]$Uri, [string]$Method = 'GET', [byte[]]$Body = @(), $Cookies = $null, [string]$Csrf = '', [int]$MaxBytes = 2097152, [int]$TimeoutSeconds = 30) {
    $target = $null
    if (![Uri]::TryCreate($Uri, [UriKind]::Absolute, [ref]$target) -or $target.Scheme -ne 'https' -or $target.UserInfo -or $target.Query -or $target.Fragment) { throw 'invalid TLS target' }
    $client = $null; $message = $null; $response = $null
    $previousTls = [Net.ServicePointManager]::SecurityProtocol
    try {
        Add-Type -AssemblyName System.Net.Http
        [Net.ServicePointManager]::SecurityProtocol = $previousTls -bor [Net.SecurityProtocolType]::Tls12
        $handler = New-Object Net.Http.HttpClientHandler
        $handler.AllowAutoRedirect = $false
        $handler.UseCookies = ($null -ne $Cookies)
        if ($Cookies) { $handler.CookieContainer = $Cookies }
        $client = New-Object Net.Http.HttpClient($handler)
        $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSeconds)
        $client.MaxResponseContentBufferSize = $MaxBytes
        $message = New-Object Net.Http.HttpRequestMessage
        $message.RequestUri = $target
        $message.Method = New-Object Net.Http.HttpMethod($Method)
        [void]$message.Headers.TryAddWithoutValidation('Origin',$target.GetLeftPart([UriPartial]::Authority))
        if ($Csrf) { [void]$message.Headers.TryAddWithoutValidation('X-CSRF-Token',$Csrf) }
        if ($Method -eq 'POST') {
            $message.Content = New-Object Net.Http.ByteArrayContent -ArgumentList @(,$Body)
            $message.Content.Headers.ContentType = New-Object Net.Http.Headers.MediaTypeHeaderValue('application/json')
            $message.Content.Headers.ContentType.CharSet = 'utf-8'
        }
        # ResponseContentRead includes all body reads in HttpClient's deadline and
        # MaxResponseContentBufferSize, including responses without Content-Length.
        $response = $client.SendAsync($message,[Net.Http.HttpCompletionOption]::ResponseContentRead).GetAwaiter().GetResult()
        if ([int]$response.StatusCode -notin @(200,204)) { throw 'HTTP refused' }
        $bytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
        if ($bytes.Length -gt $MaxBytes) { throw 'response limit' }
        return ,$bytes
    } finally {
        if ($response) { $response.Dispose() }; if ($message) { $message.Dispose() }; if ($client) { $client.Dispose() }
        [Net.ServicePointManager]::SecurityProtocol = $previousTls
    }
}
