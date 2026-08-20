#Requires -Version 5.1
param(
    [Parameter(Mandatory = $true)]
    [string]$SshHost,

    [string]$RemotePath = "/home/belhun/odysseus",

    [string]$RemoteName = "mini-pc",

    [string]$Branch = "belhun/playground",

    [switch]$SkipPush,

    [switch]$SkipBuild
)
<#
.SYNOPSIS
  Push the current git branch to a remote Docker Compose host and rebuild.

.DESCRIPTION
  Designed for a Linux host that already has Odysseus checked out and running
  under Docker Compose (for example the Mini PC).

  Host-local files are left alone:
    .env
    docker-compose.override.yml
    data/
    logs/

  Optional extras (PDF viewer, Office extraction) stay enabled when the host
  .env has INSTALL_OPTIONAL=true. That value is not in git.

  The remote repo must allow updating the checked-out branch:
    git config receive.denyCurrentBranch updateInstead

.EXAMPLE
  .\scripts\deploy-compose-host.ps1 -SshHost dell-mini-pc
#>

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "    OK: $Message" -ForegroundColor Green
}

function Write-Warn([string]$Message) {
    Write-Host "    WARN: $Message" -ForegroundColor Yellow
}

function Write-Err([string]$Message) {
    Write-Host "    ERROR: $Message" -ForegroundColor Red
}

function Invoke-Git([string[]]$GitArgs) {
    $output = & git @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed with exit $LASTEXITCODE"
    }
    return $output
}

$repoRoot = (Invoke-Git @("rev-parse", "--show-toplevel")).Trim()
Set-Location $repoRoot

$currentBranch = (Invoke-Git @("branch", "--show-current")).Trim()
if ($currentBranch -ne $Branch) {
    Write-Err "Checked out '$currentBranch', expected '$Branch'."
    exit 1
}

$localSha = (Invoke-Git @("rev-parse", "HEAD")).Trim()
Write-Step "Local $Branch @ $localSha"

$status = git status --porcelain
if ($LASTEXITCODE -ne 0) { throw "git status failed" }
if ($status) {
    Write-Warn "Uncommitted local files are not deployed. Commit first if you need them on the host."
    $status -split "`n" | Select-Object -First 12 | ForEach-Object { Write-Host "    $_" }
}

$remoteUrl = "${SshHost}:${RemotePath}"
$existing = git remote get-url $RemoteName 2>$null
if ($LASTEXITCODE -ne 0 -or -not $existing) {
    Write-Step "Adding git remote $RemoteName -> $remoteUrl"
    Invoke-Git @("remote", "add", $RemoteName, $remoteUrl)
} elseif ($existing.Trim() -ne $remoteUrl) {
    Write-Err "Remote '$RemoteName' is '$existing' (expected '$remoteUrl')."
    exit 1
} else {
    Write-Ok "git remote $RemoteName -> $remoteUrl"
}

if (-not $SkipPush) {
    Write-Step "Push $Branch to $RemoteName"
    Invoke-Git @("push", $RemoteName, "HEAD:refs/heads/$Branch")
    Write-Ok "Push complete"
} else {
    Write-Warn "SkipPush set; not pushing git"
}

if ($SkipBuild) {
    Write-Warn "SkipBuild set; not rebuilding Compose"
    exit 0
}

$remoteCmd = @"
set -eu
cd '$RemotePath'
echo "host HEAD=`$(git rev-parse --short HEAD) branch=`$(git branch --show-current)"
docker compose up -d --build odysseus
echo 'waiting for http://127.0.0.1:7000 ...'
ok=0
for i in `$(seq 1 60); do
  code=`$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:7000/ || true)
  if [ "`$code" = "200" ] || [ "`$code" = "302" ] || [ "`$code" = "303" ]; then
    echo "ready http_code=`$code"
    ok=1
    break
  fi
  sleep 3
done
if [ "`$ok" != "1" ]; then
  echo "app did not become ready; last http_code=`$code"
  docker compose ps odysseus
  exit 1
fi
docker compose ps odysseus
"@

Write-Step "Rebuild odysseus on $SshHost"
$remoteCmdUnix = $remoteCmd -replace "`r", ""
$remoteCmdUnix | ssh -o BatchMode=yes -o ConnectTimeout=10 $SshHost bash -s
if ($LASTEXITCODE -ne 0) {
    Write-Err "Remote rebuild failed"
    exit $LASTEXITCODE
}
Write-Ok "Host updated"
