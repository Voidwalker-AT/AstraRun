<#
.SYNOPSIS
    Launches or controls AstraRun v0.9 resident background process.
.DESCRIPTION
    Starts AstraRun with native system tray icon and global Alt+Space hotkey.
    Uses pythonw.exe by default to avoid keeping a terminal window open.
.PARAMETER Foreground
    If set, runs in the current console with standard output visible (useful for debugging).
.PARAMETER Stop
    Terminates any running AstraRun resident instances.
.PARAMETER Status
    Checks whether AstraRun is currently running.
#>

[CmdletBinding()]
param (
    [switch]$Foreground,
    [switch]$Stop,
    [switch]$Status
)

$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $PSScriptRoot

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$VenvPythonW = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
$MainScript = Join-Path $PSScriptRoot "src\astrarun\main.py"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment Python not found at: $VenvPython"
    exit 1
}

# 1. Stop command
if ($Stop) {
    Write-Host "[AstraRun] Looking for running AstraRun processes..." -ForegroundColor Cyan
    $procs = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -like "*astrarun*main.py*" -or $_.CommandLine -like "*AstraRun*main.py*"
    }
    if ($procs) {
        foreach ($p in $procs) {
            Write-Host "[AstraRun] Stopping process PID $($p.ProcessId)..." -ForegroundColor Yellow
            Stop-Process -Id $p.ProcessId -Force
        }
        Write-Host "[AstraRun] All resident instances stopped." -ForegroundColor Green
    } else {
        Write-Host "[AstraRun] No running AstraRun instances found." -ForegroundColor DarkGray
    }
    exit 0
}

# 2. Status command
if ($Status) {
    $procs = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -like "*astrarun*main.py*" -or $_.CommandLine -like "*AstraRun*main.py*"
    }
    if ($procs) {
        Write-Host "[AstraRun] Status: RUNNING (PID: $($procs.ProcessId -join ', '))" -ForegroundColor Green
    } else {
        Write-Host "[AstraRun] Status: NOT RUNNING" -ForegroundColor Red
    }
    exit 0
}

# 3. Check if already running
$running = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like "*astrarun*main.py*" -or $_.CommandLine -like "*AstraRun*main.py*"
}
if ($running) {
    Write-Host "[AstraRun] An instance is already running (PID: $($running.ProcessId -join ', '))." -ForegroundColor Yellow
    Write-Host "Press Alt+Space to summon the launcher, or run .\start-astrarun.ps1 -Stop to terminate it." -ForegroundColor Cyan
    exit 0
}

# 4. Launch AstraRun
if ($Foreground) {
    Write-Host "[AstraRun] Launching in foreground console mode..." -ForegroundColor Cyan
    & $VenvPython $MainScript
} else {
    Write-Host "[AstraRun] Starting AstraRun v0.9 resident background service..." -ForegroundColor Cyan
    $startExe = if (Test-Path $VenvPythonW) { $VenvPythonW } else { $VenvPython }
    Start-Process -FilePath $startExe -ArgumentList "`"$MainScript`"" -WorkingDirectory $PSScriptRoot
    Start-Sleep -Milliseconds 800
    Write-Host "[AstraRun] Resident service started." -ForegroundColor Green
    Write-Host "[AstraRun] Hotkey: Alt+Space | Tray Icon: Active in system notification area." -ForegroundColor Cyan
}
