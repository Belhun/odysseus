# Download HuggingFace models into F:\huggingface\hub (avoids full C: drive).
$ErrorActionPreference = "Continue"
$Python = "E:\odysseus\venv\Scripts\python.exe"
$DownloadScript = "E:\odysseus\scripts\hf_download.py"
$LogDir = "E:\odysseus\logs"
$LogFile = Join-Path $LogDir "model-downloads-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

$env:HF_HOME = "F:\huggingface"
$env:HUGGINGFACE_HUB_CACHE = "F:\huggingface\hub"
$env:HF_HUB_ENABLE_HF_TRANSFER = "1"

$repos = @(
    "Qwen/Qwen2.5-VL-3B-Instruct",
    "CohereLabs/North-Mini-Code-1.0",
    "BennyDaBall/Z-Image-Engineer-V6",
    "deepseek-ai/DeepSeek-V4-Flash",
    "deepseek-ai/DeepSeek-V4-Pro"
)

function Write-Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

Write-Log "=== Model batch download started ==="
Write-Log "Cache: $env:HUGGINGFACE_HUB_CACHE"
Write-Log "Log: $LogFile"

$failed = @()
foreach ($repo in $repos) {
    Write-Log ">>> START $repo"
    & $Python $DownloadScript $repo 2>&1 | ForEach-Object {
        Write-Log $_
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Log ">>> FAILED $repo (exit $LASTEXITCODE)"
        $failed += $repo
    } else {
        Write-Log ">>> DONE $repo"
    }
}

if ($failed.Count -gt 0) {
    Write-Log "=== Finished with failures: $($failed -join ', ') ==="
    exit 1
}

Write-Log "=== All downloads complete ==="
exit 0
