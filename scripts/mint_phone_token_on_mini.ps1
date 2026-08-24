# Agent / local: mint a phone_finance token on Mini PC Odysseus.
# Writes gitignored PhoneApp/.ody_bootstrap.json. Does not print the full token.
#
#   powershell -File scripts/mint_phone_token_on_mini.ps1
#   powershell -File scripts/run_pixel_phoneapp.ps1

param(
    [string]$Name = "Pixel PhoneApp",
    [string]$MiniHost = "dell-mini-pc",
    [string]$RemoteRepo = "~/odysseus"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$localPy = Join-Path $scriptDir "mint_phone_finance_token.py"
$outJson = Join-Path $repoRoot "PhoneApp\.ody_bootstrap.json"

if (-not (Test-Path $localPy)) {
    throw "Missing $localPy"
}

scp -o BatchMode=yes $localPy "${MiniHost}:/tmp/mint_phone_finance_token.py" | Out-Null
ssh -o BatchMode=yes $MiniHost "cd $RemoteRepo && docker compose cp /tmp/mint_phone_finance_token.py odysseus:/tmp/mint_phone_finance_token.py && docker compose exec -T -e PYTHONPATH=/app -w /app odysseus python /tmp/mint_phone_finance_token.py '$Name'" | Tee-Object -Variable minted | Out-Null
$raw = ($minted | Select-Object -Last 1).ToString()
$obj = $raw | ConvertFrom-Json
if (-not $obj.token) { throw "Mint failed: $raw" }

# Refresh in-process token cache so the new hash is accepted.
ssh -o BatchMode=yes $MiniHost "cd $RemoteRepo && docker compose restart odysseus" | Out-Null

$bootstrap = @{
    url = "https://dell-mini-pc.tailcbcc46.ts.net"
    token = $obj.token
    user = "belhun"
    tokenId = $obj.id
    scopes = $obj.scopes
}
$bootstrap | ConvertTo-Json | Set-Content -Path $outJson -Encoding utf8
Write-Output "Minted $($obj.id) prefix=$($obj.token.Substring(0,8))... wrote $outJson. Restarted odysseus."
