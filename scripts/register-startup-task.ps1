# Register: start Odysseus 5 minutes after logon (native Windows only).
#   powershell -ExecutionPolicy Bypass -File .\scripts\register-startup-task.ps1

$ErrorActionPreference = "Stop"
$taskName = "Odysseus-Startup"
$repoRoot = Split-Path -Parent $PSScriptRoot
$startupScript = Join-Path $PSScriptRoot "startup-odysseus.ps1"

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$startupScript`"" `
    -WorkingDirectory $repoRoot

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Start Odysseus (native Windows) 5 minutes after logon" `
    -Force | Out-Null

Write-Host "Registered: $taskName"
