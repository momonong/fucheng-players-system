param(
    [Parameter(Mandatory)][ValidateSet('Init','Admin','Start','Stop','Status','Logs')][string]$Action,
    [string]$EnvFile,
    [string]$Username
)
$ErrorActionPreference = 'Stop'
$kitDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
if (!$EnvFile) { $EnvFile = Join-Path $kitDirectory 'local-http.env' }
if (!(Test-Path -LiteralPath $EnvFile -PathType Leaf)) { throw 'Create local-http.env from local-http.env.example first' }
# Exactly one standalone Compose file. No Tunnel, proxy, or production env input.
$base = @('compose','--env-file',$EnvFile,'-f',(Join-Path $kitDirectory 'compose.local-http.yaml'),'--profile','local-http')
switch ($Action) {
    'Init' { & docker @base run --rm ops init }
    'Admin' {
        if (!$Username) { throw '-Username required; password is prompted privately' }
        & docker @base run --rm ops admin $Username
    }
    'Start' { & docker @base up -d --wait --wait-timeout 90 app }
    'Stop' { & docker @base stop }
    'Status' { & docker @base ps --all }
    'Logs' { & docker @base logs --tail 100 app }
}
if ($LASTEXITCODE -ne 0) { throw "Local HTTP preview operation failed ($LASTEXITCODE)" }
