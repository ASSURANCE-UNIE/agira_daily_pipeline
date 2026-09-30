# Run once from an elevated (administrator) PowerShell:
#   powershell -ExecutionPolicy Bypass -File C:\Scripts\agira_daily_pipeline\scripts\install_dagster_task.ps1
# Registers "AGIRA Dagster": starts at boot, runs whether or not the user is logged on
# (as the current user, S4U: no password stored), restarts every minute if it stops.
$ErrorActionPreference = "Stop"

$TaskName = "AGIRA Dagster"
$Root = Split-Path -Parent $PSScriptRoot
$Launcher = Join-Path $PSScriptRoot "start_dagster.ps1"
$User = [Security.Principal.WindowsIdentity]::GetCurrent().Name

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Launcher`"" `
    -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType S4U -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Force `
    -Description "Dagster webserver (http://localhost:1507) and daemon for the AGIRA daily pipeline" `
    -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Registered and started '$TaskName' as $User. UI: http://localhost:1507"
