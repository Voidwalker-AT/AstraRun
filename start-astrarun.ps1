<#
.SYNOPSIS
    Launches, inspects, or controls AstraRun resident background process.
.DESCRIPTION
    Starts AstraRun with native system tray icon, top-center command bar, and floating task HUD.
    Verifies process survival and readiness before declaring the service started.
.PARAMETER Foreground
    If set, runs in the current console with standard output visible (useful for debugging).
.PARAMETER Stop
    Gracefully terminates any running AstraRun resident instances.
.PARAMETER Status
    Checks whether AstraRun is currently running and reports PID, uptime, hotkey, and tray status.
.PARAMETER Restart
    Stops any running AstraRun instances, verifies exit, and starts a fresh instance with readiness verification.
#>

[CmdletBinding()]
param (
    [switch]$Foreground,
    [switch]$Stop,
    [switch]$Status,
    [switch]$Restart
)

# Support -Debug parameter without colliding with PowerShell built-in
if ($PSBoundParameters.ContainsKey('Debug')) {
    $Foreground = $true
}

$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $PSScriptRoot

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$VenvPythonW = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
$MainScript = Join-Path $PSScriptRoot "src\astrarun\main.py"
$InitPy = Join-Path $PSScriptRoot "src\astrarun\__init__.py"
$StateFile = Join-Path $PSScriptRoot "data\astrarun_state.json"
$LogFile = Join-Path $PSScriptRoot "logs\astrarun.log"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment Python not found at: $VenvPython"
    exit 1
}

# Resolve canonical version from src/astrarun/__init__.py
$version = "0.10.1-hotfix"
if (Test-Path $InitPy) {
    $verMatch = Select-String -Path $InitPy -Pattern '__version__\s*=\s*["'']([^"'']+)["'']'
    if ($verMatch) {
        $version = $verMatch.Matches[0].Groups[1].Value
    }
}

function Get-AstraRunProcesses {
    $found = @()
    # 1. Check state file PID
    if (Test-Path $StateFile) {
        try {
            $s = Get-Content -Raw -Path $StateFile | ConvertFrom-Json
            if ($s.pid) {
                $p = Get-Process -Id $s.pid -ErrorAction SilentlyContinue
                if ($p -and $p.ProcessName -like "*python*") {
                    $found += [int]$s.pid
                }
            }
        } catch {}
    }
    # 2. Check Win32_Process for Python processes executing main.py
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.Name -like "*python*") -and ($_.CommandLine -like "*main.py*")
    }
    if ($procs) {
        foreach ($cp in $procs) {
            $pidVal = [int]$cp.ProcessId
            if ($found -notcontains $pidVal) {
                $found += $pidVal
            }
        }
    }
    return $found
}

# 1. Stop / Restart command: Terminate existing instances and verify exit
if ($Stop -or $Restart) {
    Write-Host "[AstraRun] Looking for running AstraRun processes..." -ForegroundColor Cyan
    $procs = Get-AstraRunProcesses
    if ($procs) {
        foreach ($pidToStop in $procs) {
            Write-Host "[AstraRun] Stopping process PID $pidToStop..." -ForegroundColor Yellow
            Stop-Process -Id $pidToStop -Force -ErrorAction SilentlyContinue
        }
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        while ($sw.ElapsedMilliseconds -lt 3000) {
            $remaining = Get-AstraRunProcesses
            if (-not $remaining) { break }
            Start-Sleep -Milliseconds 100
        }
        Write-Host "[AstraRun] All resident instances stopped." -ForegroundColor Green
    } else {
        Write-Host "[AstraRun] No running AstraRun instances found." -ForegroundColor DarkGray
    }

    # Clean up state file
    if (Test-Path $StateFile) {
        Remove-Item -Path $StateFile -Force -ErrorAction SilentlyContinue
    }

    if ($Stop) {
        exit 0
    }
}

# 2. Status command: Truthfully inspect running processes and state
if ($Status) {
    $pids = Get-AstraRunProcesses
    if ($pids) {
        $pidStr = $pids -join ', '
        Write-Host "[AstraRun] Status: RUNNING" -ForegroundColor Green
        Write-Host "  PID:         $pidStr" -ForegroundColor Cyan
        Write-Host "  Version:     $version"
        try {
            $commit = git rev-parse --short HEAD 2>$null
            if ($commit) { Write-Host "  Git Commit:  $commit" }
        } catch {}

        if (Test-Path $StateFile) {
            try {
                $raw = Get-Content -Raw -Path $StateFile | ConvertFrom-Json
                Write-Host "  Readiness:   $($raw.status)" -ForegroundColor Green
                Write-Host "  Hotkey:      $($raw.hotkey)"
                Write-Host "  Tray Icon:   Active"
                Write-Host "  Started:     $($raw.started_at)"
                if ($raw.timestamp) {
                    $uptime = [int](([DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) - $raw.timestamp)
                    Write-Host "  Uptime:      ${uptime}s"
                }
            } catch {}
        }
    } else {
        Write-Host "[AstraRun] Status: NOT RUNNING" -ForegroundColor Red
        Write-Host "  Version:     $version"
    }
    exit 0
}

# 3. Check if already running (unless restarting)
$running = Get-AstraRunProcesses
if ($running) {
    Write-Host "[AstraRun] An instance is already running (PID: $($running -join ', '))." -ForegroundColor Yellow
    Write-Host "Press Alt+Space to summon the launcher, or run .\start-astrarun.ps1 -Restart to restart it." -ForegroundColor Cyan
    exit 0
}

# 4. Launch AstraRun
if ($Foreground) {
    Write-Host "[AstraRun] Launching AstraRun v$version in foreground console mode..." -ForegroundColor Cyan
    Write-Host "[AstraRun] Full stdout/stderr visible. Press Ctrl+C to terminate." -ForegroundColor DarkGray
    & $VenvPython $MainScript
    exit $LASTEXITCODE
} else {
    # Clean stale readiness file before spawn
    if (Test-Path $StateFile) {
        Remove-Item -Path $StateFile -Force -ErrorAction SilentlyContinue
    }

    Write-Host "[AstraRun] Starting AstraRun v$version resident background service..." -ForegroundColor Cyan
    $startExe = if (Test-Path $VenvPythonW) { $VenvPythonW } else { $VenvPython }
    $cmd = "`"$startExe`" `"$MainScript`""

    $spawnedPid = 0
    $proc = $null
    try {
        $wmiRes = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
            CommandLine = $cmd
            CurrentDirectory = $PSScriptRoot
        } -ErrorAction Stop
        if ($wmiRes.ReturnValue -eq 0 -and $wmiRes.ProcessId -gt 0) {
            $spawnedPid = [int]$wmiRes.ProcessId
        }
    } catch {}

    if ($spawnedPid -le 0) {
        $proc = Start-Process -FilePath $startExe -ArgumentList "`"$MainScript`"" -WorkingDirectory $PSScriptRoot -PassThru
        if ($proc -and $proc.Id -gt 0) {
            $spawnedPid = [int]$proc.Id
        }
    }

    if ($spawnedPid -le 0) {
        Write-Host "[AstraRun] FAILED: Could not spawn process." -ForegroundColor Red
        exit 1
    }

    Write-Host "[AstraRun] Process spawned. Waiting for readiness..." -ForegroundColor Cyan

    $ready = $false
    $state = $null
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $timeoutMs = 6000

    while ($sw.ElapsedMilliseconds -lt $timeoutMs) {
        # Check state file for readiness
        if (Test-Path $StateFile) {
            try {
                $candidate = Get-Content -Raw -Path $StateFile | ConvertFrom-Json
                if ($candidate.ready -eq $true -and $candidate.pid -gt 0) {
                    $runningProc = Get-Process -Id $candidate.pid -ErrorAction SilentlyContinue
                    if ($runningProc) {
                        $ready = $true
                        $state = $candidate
                        break
                    }
                }
            } catch {}
        }

        # Check if launcher stub failed immediately with error (when spawned via Start-Process)
        if ($proc -and $proc.HasExited -and $proc.ExitCode -ne 0) {
            Write-Host "[AstraRun] FAILED to start." -ForegroundColor Red
            Write-Host "[AstraRun] Launcher stub exited prematurely with code $($proc.ExitCode)." -ForegroundColor Red
            if (Test-Path $LogFile) {
                $tail = Get-Content -Path $LogFile -Tail 15
                Write-Host "[AstraRun] Recent log output:" -ForegroundColor Yellow
                $tail | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
            }
            Write-Host "[AstraRun] Log location: $LogFile" -ForegroundColor Yellow
            exit 1
        }

        Start-Sleep -Milliseconds 150
    }

    if ($ready) {
        Write-Host "[AstraRun] Ready." -ForegroundColor Green
        Write-Host "[AstraRun] PID: $($state.pid)" -ForegroundColor Green
        Write-Host "[AstraRun] Hotkey: $($state.hotkey)" -ForegroundColor Green
        Write-Host "[AstraRun] Tray: Active in system notification area." -ForegroundColor Green
        Write-Host "[AstraRun] Resident service started." -ForegroundColor Green
    } else {
        # Double check if any AstraRun process actually started
        $activePids = Get-AstraRunProcesses
        if ($activePids) {
            Write-Host "[AstraRun] Ready (detected active PID $($activePids -join ', '))." -ForegroundColor Green
            Write-Host "[AstraRun] Resident service started." -ForegroundColor Green
        } else {
            Write-Host "[AstraRun] FAILED to start: readiness handshake timed out." -ForegroundColor Red
            if (Test-Path $LogFile) {
                $tail = Get-Content -Path $LogFile -Tail 15
                Write-Host "[AstraRun] Recent log output:" -ForegroundColor Yellow
                $tail | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
            }
            exit 1
        }
    }
}
