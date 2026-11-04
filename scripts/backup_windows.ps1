# Daily AdenClean backup for Windows Task Scheduler (Windows PowerShell 5.1+).
#
# One-time, in your own PowerShell window (you type the key; it is never shown or logged):
#   powershell -ExecutionPolicy Bypass -File scripts\backup_windows.ps1 -SetKey
# The key is saved with Windows DPAPI, so only your Windows account on this PC can read it.
#
# Run a backup now (the scheduled task runs exactly this):
#   powershell -ExecutionPolicy Bypass -File scripts\backup_windows.ps1
#
# Backups contain customer and cleaner details. Keep -Destination private.

param(
    [switch]$SetKey,
    [string]$Destination = (Join-Path $env:USERPROFILE 'OneDrive\AdenCleanBackups'),
    [int]$KeepDays = 30
)

$ErrorActionPreference = 'Stop'
$keyFile = Join-Path $env:LOCALAPPDATA 'AdenClean\appwrite-backup-key.txt'

if ($SetKey) {
    New-Item -ItemType Directory -Force (Split-Path $keyFile) | Out-Null
    $secure = Read-Host 'Paste the Appwrite API key (input is hidden)' -AsSecureString
    $secure | ConvertFrom-SecureString | Set-Content -Path $keyFile -Encoding ASCII
    Write-Output "Saved encrypted key to $keyFile"
    exit 0
}

if (-not (Test-Path $keyFile)) {
    Write-Error "No saved key. Run this script once with -SetKey first."
}

$secure = Get-Content $keyFile | ConvertTo-SecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    # Set only for this process, so a local dev server never points at live data by accident.
    $env:APPWRITE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
$env:ADENCLEAN_STORAGE = 'appwrite'
$env:APPWRITE_ENDPOINT = 'https://nyc.cloud.appwrite.io/v1'
$env:APPWRITE_PROJECT_ID = '6ae7b1ed0005ab702dc9'

$repo = Split-Path $PSScriptRoot -Parent
$python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
$log = Join-Path (Split-Path $keyFile) 'backup.log'

& $python (Join-Path $repo 'export_backup.py') $Destination *>> $log
$code = $LASTEXITCODE
Remove-Item Env:APPWRITE_API_KEY

if ($code -eq 0) {
    Get-ChildItem $Destination -Filter 'adenclean-*.json' |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } |
        Remove-Item -Force
}
exit $code
