<# Windows-native read-only preflight, then upload even when checks say FAIL. #>
[CmdletBinding()]
param(
    [string]$ConfigFile,
    [string]$OutputDir,
    [string]$RetryReportDirectory,
    [switch]$SkipNetwork,
    [string]$ImageRef,
    [string]$ComposeProject,
    [string]$Domain,
    [string]$PreviewOrigin,
    [string]$BasePath = ''
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if (!$ConfigFile) { $ConfigFile = Join-Path $root 'private/club-report.json' }
if ($RetryReportDirectory) {
    if ($OutputDir -or $SkipNetwork -or $ImageRef -or $ComposeProject -or $Domain -or $PreviewOrigin -or $BasePath) {
        throw 'Retry only resends the original report. Do not combine retry with new preflight options.'
    }
    $output = [IO.Path]::GetFullPath($RetryReportDirectory)
} else {
    if (!$ImageRef -and (Test-Path -LiteralPath $ConfigFile)) {
        try { $configuration = [IO.File]::ReadAllText([IO.Path]::GetFullPath($ConfigFile), [Text.Encoding]::UTF8) | ConvertFrom-Json }
        catch { throw '私密設定格式不正確；請管理者核對，不要貼出 token。' }
        $ImageRef = [string]$configuration.image_ref
    }
    if (!$ImageRef) { $ImageRef = 'momonong/fucheng-players-system@sha256:faaa578ad5fa48a642f6ee80892986b20af82286111bf9f1f5309556236752cd' }
    if (!$OutputDir) {
        $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
        $OutputDir = Join-Path $root ('data/host-report-' + $stamp + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8))
    }
    $output = [IO.Path]::GetFullPath($OutputDir)
    $options = @{OutputDir=$output; ProbeNetwork=(!$SkipNetwork); BasePath=$BasePath; ImageRef=$ImageRef}
    if ($ComposeProject) { $options.ComposeProject = $ComposeProject }
    if ($Domain) { $options.Domain = $Domain }
    if ($PreviewOrigin) { $options.PreviewOrigin = $PreviewOrigin }
    & (Join-Path $PSScriptRoot 'host-preflight.ps1') @options
    if (!(Test-Path -LiteralPath (Join-Path $output 'report.json')) -or
        !(Test-Path -LiteralPath (Join-Path $output 'report.md'))) { throw 'Preflight report is incomplete; upload was not started.' }
}
Write-Output "本機報告保留於：$output"
& (Join-Path $PSScriptRoot 'send-host-report.ps1') -ReportDirectory $output -ConfigFile $ConfigFile
exit $LASTEXITCODE
