<#
Starts Redis (from ./redis-server) if not already running, waits for port 6379,
then sets the GStreamer env vars and runs OpenOB using the venv Python.

Usage examples (run from repository root):
  # Run in foreground (shows OpenOB logs)
  .\scripts\start_redis_and_openob.ps1

  # Run OpenOB with custom args (foreground)
  .\scripts\start_redis_and_openob.ps1 -OpenobArgs '-v 127.0.0.1 emetteur transmission tx 192.168.8.17 -e pcm -r 48000 -j 60 -a test'

  # Start OpenOB in background
  .\scripts\start_redis_and_openob.ps1 -Background

#>
[CmdletBinding()]
param(
    [string]$RedisExe = '.\redis-server\redis-server.exe',
    [string]$RedisConf = '.\redis-server\redis.network.conf',
    [string]$VenvPython = '.\.venv\Scripts\python.exe',
    [string]$OpenobScript = '.\.venv\Scripts\openob',
    [string]$GstBin = 'C:\Program Files\gstreamer\1.0\msvc_x86_64\bin',
    [string]$GstGir = 'C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0',
    [string]$OpenobArgs = '-v 127.0.0.1 emetteur transmission tx 192.168.8.17 -e pcm -r 48000 -j 60 -a test',
    [switch]$Background
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "Working directory: $(Get-Location)"

function Start-RedisIfNeeded {
    if (Get-Process -Name redis-server -ErrorAction SilentlyContinue) {
        Write-Host "Redis already running (process found)."
        return
    }

    if (-not (Test-Path $RedisExe)) {
        throw "redis-server.exe not found at path: $RedisExe"
    }

    Write-Host "Starting Redis from $RedisExe (config: $RedisConf)"
    $proc = Start-Process -FilePath $RedisExe -ArgumentList $RedisConf -NoNewWindow -PassThru
    Write-Host "Redis started, PID=$($proc.Id)"
}

function Wait-For-Redis {
    Write-Host 'Waiting for Redis to listen on 127.0.0.1:6379...'
    for ($i = 0; $i -lt 30; $i++) {
        $t = Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -WarningAction SilentlyContinue
        if ($t.TcpTestSucceeded) {
            Write-Host 'Redis is listening.'
            return
        }
        Start-Sleep -Seconds 1
    }
    throw 'Timed out waiting for Redis to listen on port 6379.'
}

function Run-Openob {
    Write-Host "Ensuring GStreamer env vars: PATH += $GstBin and GI_TYPELIB_PATH = $GstGir"
    $env:PATH = $env:PATH + ";$GstBin"
    $env:GI_TYPELIB_PATH = $GstGir

    if (-not (Test-Path $VenvPython)) {
        throw "Python executable not found in venv at: $VenvPython"
    }
    if (-not (Test-Path $OpenobScript)) {
        Write-Host "Warning: openob script not found at $OpenobScript. Attempting to run via pip entry point may still work."
    }

    $argsList = $OpenobArgs -split ' '

    if ($Background) {
        Write-Host 'Launching OpenOB in background (no console).'
        $argString = "$OpenobScript $OpenobArgs"
        Start-Process -FilePath $VenvPython -ArgumentList $argString -NoNewWindow -PassThru | Out-Null
        Write-Host 'OpenOB started in background.'
    }
    else {
        Write-Host "Running: $VenvPython $OpenobScript $OpenobArgs"
        & $VenvPython $OpenobScript $argsList
    }
}

Start-RedisIfNeeded
Wait-For-Redis
Run-Openob

Write-Host 'Done.'
