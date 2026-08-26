# Rewrite sensitive strings across full git history before pushing to GitHub.
# Requires: pip install git-filter-repo
#
#   powershell -ExecutionPolicy Bypass -File scripts/security/scrub-git-history.ps1
#
# After it finishes, force-push every remote branch you publish:
#   git push origin --force --all
#   git push origin --force --tags

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

$replacements = Join-Path $PSScriptRoot "filter-repo-replacements.txt"
if (-not (Test-Path $replacements)) {
    throw "Missing $replacements"
}

$filterRepo = Get-Command git-filter-repo -ErrorAction SilentlyContinue
if (-not $filterRepo) {
    throw "git-filter-repo not found. Install: pip install git-filter-repo"
}

Write-Host "Rewriting git history (this rewrites all commits)..."
git filter-repo --force --replace-text $replacements
Write-Host "Done. Review with: git log -1 --oneline && git grep dell-mini-pc"
Write-Host "Then force-push remotes you control."
