# Start native Windows Ollama with AMD GPU hints for Odysseus (Docker).
# Models live on F: (see OLLAMA_MODELS). Listens on all interfaces for Docker.

$ErrorActionPreference = "Stop"

$ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (-not (Test-Path $ollamaExe)) {
    $ollamaExe = (Get-Command ollama -ErrorAction SilentlyContinue).Source
}
if (-not $ollamaExe) {
    Write-Error "Ollama not found. Install from https://ollama.com/download or: winget install Ollama.Ollama"
}

$modelsPath = if ($env:OLLAMA_MODELS) { $env:OLLAMA_MODELS } else { "F:\ollama\models" }
if (-not (Test-Path $modelsPath)) {
    New-Item -ItemType Directory -Path $modelsPath -Force | Out-Null
}

$env:OLLAMA_GPU_OVERIDE = "vulkan"
$env:OLLAMA_HOST = "0.0.0.0:11434"
$env:OLLAMA_ORIGINS = "*"
$env:OLLAMA_MODELS = $modelsPath

Write-Host "Starting Ollama on $env:OLLAMA_HOST"
Write-Host "Models: $env:OLLAMA_MODELS"
Write-Host "GPU: OLLAMA_GPU_OVERIDE=vulkan (AMD on Windows)"
& $ollamaExe serve
