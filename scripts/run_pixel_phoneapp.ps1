# Install PhoneApp on the wireless Pixel with Mini PC bootstrap.
# Token stays in PhoneApp/.ody_bootstrap.json (gitignored). This script never prints it.
#
#   powershell -File scripts/mint_phone_token_on_mini.ps1
#   powershell -File scripts/run_pixel_phoneapp.ps1
#
# Mint + run:
#   powershell -File scripts/run_pixel_phoneapp.ps1 -MintFirst

param(
    [switch]$MintFirst
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$appDir = Join-Path $repoRoot "PhoneApp"
$bootFile = Join-Path $appDir ".ody_bootstrap.json"

if ($MintFirst) {
    & (Join-Path $scriptDir "mint_phone_token_on_mini.ps1")
}

if (-not (Test-Path $bootFile)) {
    throw "Missing $bootFile. Run scripts/mint_phone_token_on_mini.ps1 first."
}

$env:JAVA_HOME = "F:\Java\jdk-21.0.12"
$env:ANDROID_HOME = "F:\AndroidSDKManager"
$env:ANDROID_SDK_ROOT = "F:\AndroidSDKManager"
$env:PATH = "F:\FlutterDev\flutter\bin;F:\Java\jdk-21.0.12\bin;F:\AndroidSDKManager\platform-tools;" + $env:PATH

$boot = Get-Content $bootFile -Raw | ConvertFrom-Json
if (-not $boot.token) { throw "Bootstrap file has no token" }

$adb = Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"
$devices = & $adb devices
$dev = ($devices | Select-String "device$").Line.Split("`t")[0]
if (-not $dev) { throw "No ADB device. Enable wireless debugging on the Pixel." }

Set-Location $appDir
$definesFile = Join-Path $appDir ".ody_dart_defines.json"
$defines = @{
    ODY_URL = $boot.url
    ODY_TOKEN = $boot.token
    ODY_USER = $boot.user
}
if ($boot.magicdns_host) { $defines["ODY_MAGICDNS_HOST"] = [string]$boot.magicdns_host }
if ($boot.tailscale_ip) { $defines["ODY_TAILSCALE_IP"] = [string]$boot.tailscale_ip }
[System.IO.File]::WriteAllText($definesFile, ($defines | ConvertTo-Json))
Write-Output "flutter run on $dev url=$($boot.url) user=$($boot.user) tokenPrefix=$($boot.token.Substring(0,8))..."
& flutter run -d $dev --dart-define-from-file=$definesFile
