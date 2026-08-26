# One-time setup: user env vars for native Ollama + AMD GPU on Windows.
$ErrorActionPreference = "Stop"

$modelsPath = "F:\ollama\models"
if (-not (Test-Path $modelsPath)) {
    New-Item -ItemType Directory -Path $modelsPath -Force | Out-Null
}

[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "127.0.0.1:11434", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_GPU_OVERIDE", "vulkan", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_ORIGINS", "*", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $modelsPath, "User")

Write-Host "Set user environment variables:"
Write-Host "  OLLAMA_HOST=127.0.0.1:11434"
Write-Host "  OLLAMA_GPU_OVERIDE=vulkan"
Write-Host "  OLLAMA_MODELS=$modelsPath"
Write-Host ""
Write-Host "Quit Ollama from the system tray, then start it again (or run scripts\start-ollama-gpu.ps1)."
