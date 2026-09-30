# Starts the Dagster daemon (runs the schedules), webserver (UI on port 1507) and the
# read-only response viewer (port set in response_viewer\.streamlit\config.toml).
# Exits when any process stops, so the scheduled task can restart all three.
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Port = 1507
$Scripts = Join-Path $Root ".venv\Scripts"
$Home_ = Join-Path $Root ".dagster"
$Logs = Join-Path $Home_ "logs"
$ViewerDir = Join-Path $Root "response_viewer"
# Streamlit comes from the venv (the `viewer` extra): the service account has no uv of its own.
$Streamlit = Join-Path $Scripts "streamlit.exe"

Set-Location $Root
New-Item -ItemType Directory -Force $Logs | Out-Null
$config = Join-Path $Home_ "dagster.yaml"
if (-not (Test-Path $config)) { New-Item -ItemType File $config | Out-Null }

# Kill leftovers from a previous launch before starting. If the wrapper was killed hard (service stop,
# crash), its `finally` never ran and the old webserver keeps port 1507: every new launch then fails to
# bind, exits, gets restarted, and leaks another daemon + code server + run workers each time.
# The venv's python.exe is a launcher for the real interpreter in .python\, so match both.
$prefixes = @((Join-Path $Root ".venv") + "\", (Join-Path $Root ".python") + "\")
$stale = @(Get-CimInstance Win32_Process | Where-Object {
    $exe = $_.ExecutablePath; $exe -and ($prefixes | Where-Object { $exe.StartsWith($_, "OrdinalIgnoreCase") })
} | ForEach-Object ProcessId)
$stale += @(Get-NetTCPConnection -State Listen -LocalPort $Port, 1508 -ErrorAction SilentlyContinue | ForEach-Object OwningProcess)
foreach ($id in ($stale | Where-Object { $_ -and $_ -ne $PID } | Sort-Object -Unique)) {
    taskkill.exe /PID $id /T /F 2>$null | Out-Null
}

$env:DAGSTER_HOME = $Home_
$env:PYTHONLEGACYWINDOWSSTDIO = "1"  # enables Dagster compute-log capture on Windows
$env:PYTHONUTF8 = "1"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$module = @("-m", "agira_daily.definitions")

$daemon = $web = $viewer = $null
# Starts happen inside the try so a failed start (e.g. a missing exe) still stops the ones already running.
try {
    $daemon = Start-Process -FilePath (Join-Path $Scripts "dagster-daemon.exe") `
        -ArgumentList (@("run") + $module) -WorkingDirectory $Root -NoNewWindow -PassThru `
        -RedirectStandardOutput (Join-Path $Logs "daemon-$stamp.out.log") `
        -RedirectStandardError (Join-Path $Logs "daemon-$stamp.err.log")

    $web = Start-Process -FilePath (Join-Path $Scripts "dagster-webserver.exe") `
        -ArgumentList ($module + @("-h", "0.0.0.0", "-p", "$Port")) -WorkingDirectory $Root -NoNewWindow -PassThru `
        -RedirectStandardOutput (Join-Path $Logs "webserver-$stamp.out.log") `
        -RedirectStandardError (Join-Path $Logs "webserver-$stamp.err.log")

    # Runs from response_viewer\ so Streamlit picks up its .streamlit\config.toml.
    $viewer = Start-Process -FilePath $Streamlit -ArgumentList @("run", "app.py") `
        -WorkingDirectory $ViewerDir -NoNewWindow -PassThru `
        -RedirectStandardOutput (Join-Path $Logs "viewer-$stamp.out.log") `
        -RedirectStandardError (Join-Path $Logs "viewer-$stamp.err.log")

    while (-not ($daemon.HasExited -or $web.HasExited -or $viewer.HasExited)) { Start-Sleep -Seconds 10 }
} catch {
    # Service stdout/stderr may go nowhere, so leave the reason next to the process logs.
    "$(Get-Date -Format s) $_" | Out-File -Append -Encoding utf8 (Join-Path $Logs "start_dagster.err.log")
} finally {
    foreach ($p in $daemon, $web, $viewer) {
        # /T also stops child processes, so the ports are free on restart.
        if ($p -and -not $p.HasExited) { taskkill.exe /PID $p.Id /T /F | Out-Null }
    }
}
exit 1  # reaching here means a process died; let Task Scheduler restart us
