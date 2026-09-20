param([string]$Directory, [Parameter(Mandatory)][string]$Image)
$ErrorActionPreference='Stop'
if (!$Directory) { $Directory = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'secrets/test-tls' }
$Directory=[IO.Path]::GetFullPath($Directory)
if (Test-Path -LiteralPath $Directory) { throw 'TLS output directory exists; refusing overwrite' }
New-Item -ItemType Directory -Path $Directory | Out-Null
# Use the already loaded app image, with no network or dependency installation.
& docker run --rm --network none --pull never --user 10001:10001 --mount "type=bind,source=$Directory,target=/certs" --entrypoint openssl $Image req -x509 -newkey rsa:2048 -nodes -days 30 -keyout /certs/key.pem -out /certs/cert.pem -subj /CN=localhost -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1'
if ($LASTEXITCODE -ne 0) { throw 'Local test certificate generation failed' }
Write-Output "Local test-only certificate: $Directory. Not installed or trusted globally."
