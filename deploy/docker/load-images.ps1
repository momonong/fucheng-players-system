param([string]$Directory)
$ErrorActionPreference='Stop'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
if (!$Directory) { $Directory = Split-Path -Parent $MyInvocation.MyCommand.Path }
$Directory = [IO.Path]::GetFullPath($Directory)
foreach ($line in Get-Content -LiteralPath (Join-Path $Directory 'SHA256SUMS.txt')) {
    $hash,$name = $line -split '  ',2
    if ([IO.Path]::GetFileName($name) -ne $name) { throw 'Invalid checksum path' }
    if ((Get-FileHash -LiteralPath (Join-Path $Directory $name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hash) { throw "Checksum mismatch: $name" }
}
$release = Get-Content -LiteralPath (Join-Path $Directory 'release.json') -Raw | ConvertFrom-Json
& docker load --input (Join-Path $Directory 'fucheng-images.tar')
if ($LASTEXITCODE -ne 0) { throw 'Docker load failed' }
$images = @([pscustomobject]@{tag=$release.image; image_id=$release.image_id}) + @($release.offline_support)
foreach ($item in $images) {
    $actual = & docker image inspect $item.tag --format '{{.Id}}'
    if ($LASTEXITCODE -ne 0 -or $actual -ne $item.image_id) { throw "Image ID mismatch: $($item.tag)" }
}
Write-Output 'All archive checksums and loaded image IDs verified. No registry push or tunnel start performed.'
