param(
    [Parameter(Mandatory)][ValidateSet('Init','RecoverInit','Admin','Start','StartTest','StartCloudflare','StartNgrok','Stop','Status','Logs','Backup','ImportBackup','Migrate','Restore','ExportBackups')][string]$Action,
    [string]$EnvFile,
    [string]$Value
)
$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
$kitDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
if (!$EnvFile) { $EnvFile = Join-Path $kitDirectory 'release.env' }
if (!(Test-Path -LiteralPath $EnvFile -PathType Leaf)) { throw 'Create release.env from release.env.example first' }
$base = @('compose','--env-file',$EnvFile,'-f',(Join-Path $kitDirectory 'compose.yaml'),'-f',(Join-Path $kitDirectory 'compose.ngrok.yaml'))
function Invoke-Compose([string[]]$Tail) {
    & docker @base @Tail
    if ($LASTEXITCODE -ne 0) { throw "Compose failed ($LASTEXITCODE); keep maintenance state and inspect logs" }
}
switch ($Action) {
    'Init' { Invoke-Compose @('run','--rm','ops','init') }
    'RecoverInit' { Invoke-Compose @('run','--rm','ops','recover-init') }
    'Admin' {
        if (!$Value) { throw '-Value requires the administrator username; password will be prompted privately' }
        Invoke-Compose @('run','--rm','ops','admin',$Value)
    }
    'Start' { Invoke-Compose @('up','-d','--wait','--wait-timeout','90','app','backup') }
    'StartTest' { Invoke-Compose @('--profile','https-test','up','-d','--wait','--wait-timeout','90','app','backup','https-test') }
    'StartCloudflare' { Invoke-Compose @('--profile','cloudflare','up','-d','--wait','--wait-timeout','90','app','backup','cloudflared') }
    'StartNgrok' {
        Invoke-Compose @('--profile','ngrok','up','-d','--wait','--wait-timeout','90','app','backup','ngrok')
    }
    'Stop' { Invoke-Compose @('--profile','https-test','--profile','cloudflare','--profile','ngrok','stop') }
    'Status' { Invoke-Compose @('ps','--all') }
    'Logs' { Invoke-Compose @('logs','--tail','100','app','backup') }
    'Backup' { Invoke-Compose @('run','--rm','ops','backup') }
    'ImportBackup' {
        if (!$Value) { throw '-Value requires the returned DB path, with its matching .json metadata next to it' }
        $source = Get-Item -LiteralPath $Value
        if ($source.Extension -ne '.db') { throw 'Expected a .db backup' }
        $metaPath = [IO.Path]::ChangeExtension($source.FullName,'.json')
        $metadata = Get-Content -LiteralPath $metaPath -Raw | ConvertFrom-Json
        if ($metadata.file -ne $source.Name -or (Get-FileHash -LiteralPath $source.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $metadata.sha256) { throw 'Backup metadata/checksum mismatch' }
        Invoke-Compose @('run','--rm','--volume',"$($source.DirectoryName):/incoming:ro",'ops','import-backup',$source.Name)
    }
    'Migrate' { Invoke-Compose @('run','--rm','ops','migrate') }
    'Restore' {
        if (!$Value -or [IO.Path]::GetFileName($Value) -ne $Value) { throw '-Value requires only a backup filename, never a destination to overwrite' }
        Invoke-Compose @('run','--rm','ops','restore',$Value)
    }
    'ExportBackups' {
        if (!$Value) { throw '-Value requires a NEW export directory, preferably on a separately managed disk' }
        $destination = [IO.Path]::GetFullPath($Value)
        if (Test-Path -LiteralPath $destination) { throw 'Export refuses existing directories' }
        # Runtime holds backup.lock while snapshotting and archiving completed DB/metadata pairs.
        $raw = & docker @base run --rm ops export
        if ($LASTEXITCODE -ne 0) { throw 'Consistent export failed; no successful export claimed' }
        $export = $raw | ConvertFrom-Json
        $id = & docker @base ps -a -q app
        if ($LASTEXITCODE -ne 0 -or !$id) { throw 'Create the app container first so the named backup volume can be exported' }
        New-Item -ItemType Directory -Path $destination | Out-Null
        $archive = Join-Path $destination $export.archive
        & docker cp "${id}:/backups/exports/$($export.archive)" $archive
        if ($LASTEXITCODE -ne 0) { throw 'Backup export failed; the incomplete destination was retained' }
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $export.sha256) { throw 'Export archive checksum failed' }
        $raw | Set-Content -LiteralPath (Join-Path $destination 'export-manifest.json') -Encoding utf8
        & tar -xf $archive -C $destination
        if ($LASTEXITCODE -ne 0) { throw 'Export extraction failed; retained files require inspection' }
        foreach ($property in $export.files.PSObject.Properties) {
            if ((Get-FileHash -LiteralPath (Join-Path $destination $property.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $property.Value) { throw 'Export member checksum failed' }
        }
        Write-Output "Verified export: $destination. Same-disk copies are NOT offsite backups. Protect member data and credentials in this export."
    }
}
