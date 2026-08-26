# Create local/deploy.json from example or existing bootstrap files (one-time setup).
#
#   powershell -File scripts/init-local-deploy.ps1

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$outPath = Join-Path $repoRoot "local\deploy.json"
$examplePath = Join-Path $repoRoot "local\deploy.json.example"
$phoneBoot = Join-Path $repoRoot "PhoneApp\.ody_bootstrap.json"
$phonePiBoot = Join-Path $repoRoot ".phonepi_bootstrap.json"

if (Test-Path $outPath) {
    Write-Output "Already exists: $outPath"
    exit 0
}

if (-not (Test-Path (Join-Path $repoRoot "local"))) {
    New-Item -ItemType Directory -Path (Join-Path $repoRoot "local") | Out-Null
}

$cfg = @{
    odysseus_url = "https://your-host.tailXXXXXX.ts.net"
    magicdns_host = "your-host.tailXXXXXX.ts.net"
    tailscale_ip = "100.x.y.z"
    odysseus_user = "youruser"
    ssh_host = "your-mini-host"
    remote_repo = "~/odysseus"
    remote_path = "/home/youruser/odysseus"
    git_branch = "main"
}

if (Test-Path $phoneBoot) {
    $boot = Get-Content $phoneBoot -Raw | ConvertFrom-Json
    if ($boot.url) {
        $cfg.odysseus_url = [string]$boot.url
        try {
            $u = [Uri]$boot.url
            $cfg.magicdns_host = $u.Host
            $shortHost = $u.Host.Split('.')[0]
            if ($shortHost) { $cfg.ssh_host = $shortHost }
        } catch { }
    }
    if ($boot.user) { $cfg.odysseus_user = [string]$boot.user }
}

if (Test-Path $phonePiBoot) {
    $pi = Get-Content $phonePiBoot -Raw | ConvertFrom-Json
    if ($pi.host) {
        $cfg.magicdns_host = [string]$pi.host
        $shortHost = ([string]$pi.host).Split('.')[0]
        if ($shortHost) { $cfg.ssh_host = $shortHost }
        if (-not $cfg.odysseus_url.StartsWith("https://")) {
            $cfg.odysseus_url = "https://$($pi.host)"
        }
    }
}

if (Test-Path $examplePath) {
    $example = Get-Content $examplePath -Raw | ConvertFrom-Json
    foreach ($prop in $example.PSObject.Properties) {
        $key = $prop.Name
        $cur = $cfg[$key]
        if ($cur -like "*your-*" -or $cur -like "*XXXXXX*" -or $cur -eq "100.x.y.z" -or $cur -eq "youruser") {
            if ($prop.Value) { $cfg[$key] = [string]$prop.Value }
        }
    }
}

$cfg | ConvertTo-Json | Set-Content -Path $outPath -Encoding utf8
Write-Output "Wrote $outPath - edit hostnames and ssh_host before running deploy/mint scripts."
