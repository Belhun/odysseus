# Rebuild/install PhonePi on the wireless Pixel, then launch it with the Mini PC setup link.
# Token-free. Host/port live in gitignored .phonepi_bootstrap.json.
#
#   powershell -File scripts/mint_phonepi_connect_on_mini.ps1
#   powershell -File scripts/run_pixel_phonepi.ps1
#
# Mint + run:
#   powershell -File scripts/run_pixel_phonepi.ps1 -MintFirst

param(
    [switch]$MintFirst,
    [string]$PhonePiDir = "F:\Codeing Project\phonepi-mcp\phonepi-android"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$bootFile = Join-Path $repoRoot ".phonepi_bootstrap.json"

if ($MintFirst) {
    & (Join-Path $scriptDir "mint_phonepi_connect_on_mini.ps1")
}

$env:JAVA_HOME = "F:\Java\jdk-21.0.12"
$env:ANDROID_HOME = "F:\AndroidSDKManager"
$env:ANDROID_SDK_ROOT = "F:\AndroidSDKManager"
$env:PATH = "F:\Java\jdk-21.0.12\bin;F:\AndroidSDKManager\platform-tools;" + $env:PATH

$adb = Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"
if (-not (Test-Path $adb)) { throw "adb not found at $adb" }

$mdns = "adb-4A301FDAS001MW-u8mLeM._adb-tls-connect._tcp"
& $adb connect $mdns | Out-Null
Start-Sleep -Seconds 1
$devices = & $adb devices
$dev = ($devices | Select-String "device$").Line
if (-not $dev) {
    & $adb connect "192.168.1.226:41687" | Out-Null
    Start-Sleep -Seconds 1
    $devices = & $adb devices
    $dev = ($devices | Select-String "device$").Line
}
if (-not $dev) { throw "No ADB device. Enable wireless debugging on the Pixel." }
$serial = $dev.ToString().Split("`t")[0]
Write-Output "ADB device $serial"

if (-not (Test-Path $PhonePiDir)) { throw "Missing PhonePi project $PhonePiDir" }
$apk = Join-Path $PhonePiDir "app\build\outputs\apk\debug\app-debug.apk"
Push-Location $PhonePiDir
try {
    & .\gradlew.bat assembleDebug
    if ($LASTEXITCODE -ne 0) { throw "Gradle build failed" }
} finally {
    Pop-Location
}

& $adb -s $serial install -r $apk
if ($LASTEXITCODE -ne 0) { throw "adb install failed" }

$deeplink = "phonepi://setup?host=dell-mini-pc.tailcbcc46.ts.net&port=443"
if (Test-Path $bootFile) {
    $boot = Get-Content $bootFile -Raw | ConvertFrom-Json
    if ($boot.deeplink) { $deeplink = [string]$boot.deeplink }
}
Write-Output "Launching PhonePi with $deeplink"
# Quote the URI inside Android sh so Windows cmd and the remote shell keep &port=.
& $adb -s $serial shell "am start -a android.intent.action.VIEW -d '$deeplink'"
Write-Output "Installed and launched. Watch logcat: adb -s $serial logcat -s PhonePiWS:I"
