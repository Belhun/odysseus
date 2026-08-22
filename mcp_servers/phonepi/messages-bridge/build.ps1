$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    go build -o phonepi-gmessages.exe .
    if ($LASTEXITCODE -ne 0) { throw "go build failed" }
    Write-Host "Built messages-bridge\phonepi-gmessages.exe"
} finally {
    Pop-Location
}
