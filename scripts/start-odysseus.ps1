# Manual start: native Ollama (GPU) + Odysseus in Docker.
# Double-click the desktop shortcut or run:
#   powershell -ExecutionPolicy Bypass -File .\scripts\start-odysseus.ps1

param([switch]$NoPrompt)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Write-Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

Write-Step "Starting Ollama (Windows)"
$ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (-not (Test-Path $ollamaExe)) {
    Write-Host "Ollama not installed. Get it from https://ollama.com/download" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

$env:OLLAMA_MODELS = [Environment]::GetEnvironmentVariable("OLLAMA_MODELS", "User")
if (-not $env:OLLAMA_MODELS) { $env:OLLAMA_MODELS = "F:\ollama\models" }
$env:OLLAMA_HOST = "127.0.0.1:11434"
$env:OLLAMA_GPU_OVERIDE = "vulkan"

$ollamaUp = $false
try {
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
    if ($tags.models.Count -gt 0) {
        $ollamaUp = $true
        Write-Host "Ollama already running ($($tags.models.Count) models on $env:OLLAMA_MODELS)"
    }
} catch { }

if (-not $ollamaUp) {
    Get-Process -Name "ollama*" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
    Write-Host "Waiting for Ollama..."
    $ready = $false
    foreach ($i in 1..30) {
        Start-Sleep -Seconds 1
        try {
            $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2
            if ($tags.models.Count -ge 0) { $ready = $true; break }
        } catch { }
    }
    if (-not $ready) {
        Write-Host "Ollama did not respond on :11434" -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit 1
    }
    Write-Host "Ollama ready ($($tags.models.Count) models)"
}

Write-Step "Starting Odysseus (Docker)"
docker compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "docker compose failed. Is Docker Desktop running?" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

Write-Step "Done"
Write-Host "Open:  http://127.0.0.1:7000" -ForegroundColor Green
Write-Host "Login: admin (password from first setup — see docker compose logs odysseus)"
if (-not $NoPrompt) {
    Start-Process "http://127.0.0.1:7000"
    Write-Host ""
    Read-Host "Press Enter to close this window (Ollama and Docker keep running)"
}
