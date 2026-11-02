<# Paste into native Windows PowerShell, or run this launcher in the ready folder. #>
& {
$ErrorActionPreference = 'Stop'
try {
    if ($PSScriptRoot -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'RUN-CHECK.cmd'))) { $folder = $PSScriptRoot }
    else { $folder = Join-Path ([Environment]::GetFolderPath('Desktop')) 'fucheng-check-v120-ready' }
    $entry = Join-Path $folder 'RUN-CHECK.cmd'
    if (!(Test-Path -LiteralPath $entry -PathType Leaf)) {
        Add-Type -AssemblyName System.Windows.Forms
        $picker = New-Object Windows.Forms.OpenFileDialog
        $picker.Title = '請選取已傳送 ready 資料夾內的 RUN-CHECK.cmd'
        $picker.Filter = '球館一次健檢入口 (RUN-CHECK.cmd)|RUN-CHECK.cmd'
        if ($picker.ShowDialog() -ne 'OK') { throw 'selection cancelled' }
        $folder = [IO.Path]::GetDirectoryName($picker.FileName)
        $picker.Dispose()
    }
    $runner = Join-Path $folder 'deploy/docker/club-host-one-shot.ps1'
    if (!(Test-Path -LiteralPath $runner -PathType Leaf)) { throw 'runner absent' }
    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $runner
} catch {
    Write-Host '尚未啟動健檢。請先將完整私密 ready 資料夾傳到球館電腦，再重貼本段；不要貼出 token。'
}
}
