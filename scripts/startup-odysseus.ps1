# Waits 5 minutes after logon, then starts Odysseus (native Windows).

$ErrorActionPreference = "Stop"
Start-Sleep -Seconds 300

$repoRoot = Split-Path -Parent $PSScriptRoot
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoRoot "launch-windows.ps1")
