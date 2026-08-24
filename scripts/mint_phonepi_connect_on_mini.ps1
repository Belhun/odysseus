# Agent / local: write PhonePi connect hint from Mini PC Odysseus.
# PhonePi has no ody_ token; the tailnet is the gate. Writes gitignored .phonepi_bootstrap.json.
#
#   powershell -File scripts/mint_phonepi_connect_on_mini.ps1
#   powershell -File scripts/run_pixel_phonepi.ps1

param(
    [string]$MiniHost = "dell-mini-pc",
    [string]$RemoteRepo = "~/odysseus"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$localPy = Join-Path $scriptDir "mint_phonepi_connect.py"
$outJson = Join-Path $repoRoot ".phonepi_bootstrap.json"

if (-not (Test-Path $localPy)) {
    throw "Missing $localPy"
}

scp -o BatchMode=yes $localPy "${MiniHost}:/tmp/mint_phonepi_connect.py" | Out-Null
$minted = ssh -o BatchMode=yes $MiniHost "cd $RemoteRepo && docker compose cp /tmp/mint_phonepi_connect.py odysseus:/tmp/mint_phonepi_connect.py && docker compose exec -T -e PYTHONPATH=/app -w /app odysseus python /tmp/mint_phonepi_connect.py"
$raw = ($minted | Select-Object -Last 1).ToString()
$obj = $raw | ConvertFrom-Json
if (-not $obj.deeplink) { throw "PhonePi connect mint failed: $raw" }

$obj | ConvertTo-Json | Set-Content -Path $outJson -Encoding utf8
Write-Output "PhonePi host=$($obj.host) port=$($obj.port) wrote $outJson"
