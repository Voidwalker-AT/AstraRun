<#
.SYNOPSIS
    Creates or updates the Windows desktop/project shortcut for AstraRun.
.DESCRIPTION
    Creates AstraRun.lnk configured to invoke pythonw.exe detached without opening any console window.
#>

$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $PSScriptRoot

$VenvPythonW = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
$MainScript = Join-Path $ProjectRoot "src\astrarun\main.py"
$IconFile = Join-Path $ProjectRoot "assets\icon.ico"
$ShortcutPath = Join-Path $ProjectRoot "AstraRun.lnk"

if (-not (Test-Path $VenvPythonW)) {
    Write-Error "Virtual environment pythonw.exe not found at: $VenvPythonW"
    exit 1
}

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $VenvPythonW
$Shortcut.Arguments = "`"$MainScript`""
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.Description = "AstraRun - Windows Intelligent Command Launcher (Alt+Space)"
if (Test-Path $IconFile) {
    $Shortcut.IconLocation = "$IconFile, 0"
}
$Shortcut.Save()

Write-Host "[AstraRun] Shortcut created successfully: $ShortcutPath" -ForegroundColor Green
Write-Host "  Target: $VenvPythonW"
Write-Host "  Args:   $MainScript"
Write-Host "  Icon:   $IconFile"
