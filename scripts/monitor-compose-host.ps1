#Requires -Version 5.1
<#
.SYNOPSIS
  Open a live Mini PC Odysseus monitor from this desktop.

.DESCRIPTION
  Copies the host script over SSH if needed, then attaches a tmux session
  with three panes: Compose logs, host/container stats, and perf.jsonl.

.EXAMPLE
  .\scripts\monitor-compose-host.ps1

.EXAMPLE
  .\scripts\monitor-compose-host.ps1 -Reset
#>
param(
    [string]$SshHost = "dell-mini-pc",
    [string]$RemotePath = "/home/belhun/odysseus",
    [string]$Session = "ody-mon",
    [switch]$Reset
)

$ErrorActionPreference = "Stop"
$localScript = Join-Path $PSScriptRoot "monitor-compose-host.sh"
if (-not (Test-Path $localScript)) {
    throw "missing $localScript"
}

$remoteTmp = "/tmp/monitor-compose-host.sh"
$remoteScript = "$RemotePath/scripts/monitor-compose-host.sh"

Write-Host "Syncing monitor script to $SshHost ..."
scp -o BatchMode=yes -o ConnectTimeout=10 -- "$localScript" "${SshHost}:${remoteTmp}"
if ($LASTEXITCODE -ne 0) { throw "scp failed" }

ssh -o BatchMode=yes -o ConnectTimeout=10 $SshHost "sed -i 's/\r`$//' '$remoteTmp' && mkdir -p '$RemotePath/scripts' && mv '$remoteTmp' '$remoteScript' && chmod +x '$remoteScript'"
if ($LASTEXITCODE -ne 0) { throw "remote install failed" }

$action = if ($Reset) { "reset" } else { "attach" }
Write-Host "Opening tmux session '$Session' on $SshHost"
Write-Host "Panes: Compose logs | host stats | perf events"
Write-Host "Detach: Ctrl-b then d   (session keeps running on the Mini PC)"
Write-Host ""

$env:ODYSSEUS_MONITOR_SESSION = $Session
ssh -t -o ConnectTimeout=10 $SshHost "ODYSSEUS_MONITOR_SESSION='$Session' bash '$remoteScript' $action"
exit $LASTEXITCODE
