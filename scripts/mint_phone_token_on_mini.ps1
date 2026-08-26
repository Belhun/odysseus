# Agent / local: mint a phone_finance token on Mini PC Odysseus.
# Writes gitignored PhoneApp/.ody_bootstrap.json. Does not print the full token.
#
#   powershell -File scripts/init-local-deploy.ps1
#   powershell -File scripts/mint_phone_token_on_mini.ps1

param(
    [string]$Name = "Pixel PhoneApp"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
. (Join-Path $scriptDir "lib\LocalDeploy.ps1")
$localPy = Join-Path $scriptDir "mint_phone_finance_token.py"
$outJson = Join-Path $repoRoot "PhoneApp\.ody_bootstrap.json"

$miniHost = Get-DeployValue -Key "ssh_host" -Default "" -RepoRoot $repoRoot
$remoteRepo = Get-DeployValue -Key "remote_repo" -Default "~/odysseus" -RepoRoot $repoRoot
$odysseusUrl = Get-DeployValue -Key "odysseus_url" -Default "" -RepoRoot $repoRoot
$odysseusUser = Get-DeployValue -Key "odysseus_user" -Default "admin" -RepoRoot $repoRoot
$magicHost = Get-DeployValue -Key "magicdns_host" -Default "" -RepoRoot $repoRoot
$tailscaleIp = Get-DeployValue -Key "tailscale_ip" -Default "" -RepoRoot $repoRoot

if (-not $miniHost -or -not $odysseusUrl) {
    throw "Configure local/deploy.json first (scripts/init-local-deploy.ps1)."
}
if (-not (Test-Path $localPy)) { throw "Missing $localPy" }

scp -o BatchMode=yes $localPy "${miniHost}:/tmp/mint_phone_finance_token.py" | Out-Null
$mintCmd = "cd $remoteRepo && docker compose cp /tmp/mint_phone_finance_token.py odysseus:/tmp/mint_phone_finance_token.py && docker compose exec -T -e PYTHONPATH=/app -e ODYSSEUS_OWNER=$odysseusUser -w /app odysseus python /tmp/mint_phone_finance_token.py '$Name'"
$minted = ssh -o BatchMode=yes $miniHost $mintCmd
$raw = ($minted | Select-Object -Last 1).ToString()
$obj = $raw | ConvertFrom-Json
if (-not $obj.token) { throw "Mint failed: $raw" }

ssh -o BatchMode=yes $miniHost "cd $remoteRepo && docker compose restart odysseus" | Out-Null

$bootstrap = @{
    url = $odysseusUrl
    token = $obj.token
    user = $odysseusUser
    tokenId = $obj.id
    scopes = $obj.scopes
    magicdns_host = $magicHost
    tailscale_ip = $tailscaleIp
} | ConvertTo-Json | Set-Content -Path $outJson -Encoding utf8
Write-Output "Minted $($obj.id) prefix=$($obj.token.Substring(0,8))... wrote $outJson."
