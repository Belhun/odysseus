# Start Odysseus (native Windows, no Docker, no Ollama).
# Desktop shortcut and delayed startup use this script.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "launch-windows.ps1")
