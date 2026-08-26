# Load gitignored local/deploy.json for personal hostnames, SSH targets, and users.
# Copy local/deploy.json.example to local/deploy.json and edit once per machine.

function Get-LocalDeployPath {
    param([string]$RepoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)))
    Join-Path $RepoRoot "local\deploy.json"
}

function Get-LocalDeploy {
    param([string]$RepoRoot)
    $path = Get-LocalDeployPath -RepoRoot $RepoRoot
    if (-not (Test-Path $path)) {
        return $null
    }
    try {
        return Get-Content $path -Raw | ConvertFrom-Json
    } catch {
        throw "Invalid JSON in $path : $_"
    }
}

function Get-DeployValue {
    param(
        [string]$Key,
        [string]$Default = "",
        [string]$RepoRoot
    )
    $cfg = Get-LocalDeploy -RepoRoot $RepoRoot
    if ($null -eq $cfg) { return $Default }
    $val = $cfg.$Key
    if ($null -eq $val -or [string]::IsNullOrWhiteSpace([string]$val)) {
        return $Default
    }
    return [string]$val
}
