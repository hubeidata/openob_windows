<#
Start OpenOB assuming Redis is already running.

Usage (from repo root):
  # run in foreground (shows logs)
  .\scripts\start_openob.ps1

  # run with custom args
  .\scripts\start_openob.ps1 -OpenobArgs '-v 127.0.0.1 emetteur transmission tx 192.168.18.37 -e pcm -r 48000 -j 60 -a auto'

  # run in background
  .\scripts\start_openob.ps1 -Background

This script assumes Redis is running locally on 127.0.0.1:6379. It sets GStreamer
environment variables for the current session and runs the OpenOB entry script
from the virtualenv.
#>

[CmdletBinding()]
param(
    [string]$VenvPython = '.\.venv\Scripts\python.exe',
    [string]$OpenobScript = '.\.venv\Scripts\openob',
    [string]$GstBin = 'C:\Program Files\gstreamer\1.0\msvc_x86_64\bin',
    [string]$GstGir = 'C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0',
    [string]$OpenobArgs = '127.0.0.1 emetteur transmission tx 192.168.18.37 -e pcm -r 48000 -j 60 -a auto',
    [switch]$Background,
    [string]$LogDir = '.\logs'
    [switch]$ForceRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "Starting OpenOB (assumes Redis already running). Working directory: $(Get-Location)"

function Check-Redis {
    $t = Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -WarningAction SilentlyContinue
    if ($t.TcpTestSucceeded) {
        Write-Host 'Redis reachable on 127.0.0.1:6379'
        return $true
    }
    Write-Warning 'Redis not reachable on 127.0.0.1:6379.'
    return $false
}

if (-not (Test-Path $VenvPython)) {
    Write-Error "Python executable not found in venv: $VenvPython. Create the venv or adjust the path."
    exit 2
}

if (-not (Test-Path $OpenobScript)) {
    Write-Warning "openob script not found at $OpenobScript. Attempting to run the installed entry point may still work."
}

$env:PATH = $env:PATH + ";$GstBin"
$env:GI_TYPELIB_PATH = $GstGir
Write-Host "GStreamer env set: PATH += $GstBin; GI_TYPELIB_PATH=$GstGir"

$redisOk = Check-Redis
if (-not $redisOk -and -not $ForceRun) {
    $yes = Read-Host 'Redis not reachable locally. Continue anyway? (y/N)'
    if ($yes -ne 'y' -and $yes -ne 'Y') { Write-Host 'Aborting.'; exit 3 }
}

$argList = $OpenobArgs -split ' '

if ($Background) {
    Write-Host "Launching OpenOB in background: $VenvPython $OpenobScript $OpenobArgs"
    $argString = "$OpenobScript $OpenobArgs"
    # Ensure log directory
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $logFile = Join-Path $LogDir "openob-$timestamp.log"

    # Build a PowerShell one-liner that runs the python command and redirects output to a log file.
    # Use single quotes carefully to avoid expansion in the wrapper; escape single quotes inside.
    $py = (Resolve-Path $VenvPython).Path
    $scriptPath = (Resolve-Path $OpenobScript).Path
    $escapedArgs = $OpenobArgs -Replace "'", "''"
    $psCommand = "& '$py' '$scriptPath' $escapedArgs *> '$logFile' 2>&1"

    Start-Process -FilePath powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-Command',$psCommand -WorkingDirectory (Get-Location).Path -PassThru | Out-Null
    Write-Host "OpenOB launched in background. Logs: $logFile"
}
else {
    Write-Host "Running OpenOB: $VenvPython $OpenobScript $OpenobArgs"
    & $VenvPython $OpenobScript $argList
}

Write-Host 'start_openob.ps1 finished.'
