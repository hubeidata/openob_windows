<#
Install Redis as a Windows service using the bundled redis-server.exe.

Usage (Run PowerShell as Administrator):
  # from repo root
  .\scripts\install_redis_service.ps1

Parameters:
  -RedisExe   Path to redis-server.exe (default: .\redis-server\redis-server.exe)
  -RedisConf  Path to redis config to install the service with (default: .\redis-server\redis.network.conf if present, else redis.windows-service.conf, else redis.windows.conf)

This script must be run as Administrator. It will stop any running redis-server process, install the Windows service and start it.
#>

[CmdletBinding()]
param(
    [string]$RedisExe = '.\redis-server\redis-server.exe',
    [string]$RedisConf
)

function Assert-Admin {
    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-Error "This script must be run as Administrator. Open an elevated PowerShell and re-run."
        exit 2
    }
}

Assert-Admin

if (-not (Test-Path $RedisExe)) {
    Write-Error "redis-server executable not found at: $RedisExe"
    exit 3
}

if (-not $RedisConf) {
    if (Test-Path '.\redis-server\redis.network.conf') { $RedisConf = '.\redis-server\redis.network.conf' }
    elseif (Test-Path '.\redis-server\redis.windows-service.conf') { $RedisConf = '.\redis-server\redis.windows-service.conf' }
    else { $RedisConf = '.\redis-server\redis.windows.conf' }
}

if (-not (Test-Path $RedisConf)) {
    Write-Error "Redis config not found at: $RedisConf"
    exit 4
}

# Resolve full paths to avoid relative-path issues when the service runs
$RedisExe = (Resolve-Path $RedisExe).ProviderPath
$RedisConf = (Resolve-Path $RedisConf).ProviderPath

Write-Host "Stopping any running redis-server processes..."
Get-Process -Name redis-server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# If a Redis service already exists, uninstall it first (to replace PathName with absolute paths)
try {
    $existing = Get-Service -Name Redis -ErrorAction Stop
    if ($existing) {
        Write-Host "Existing Redis service found (Status: $($existing.Status)). Attempting to uninstall first..."
        & $RedisExe --service-stop 2>$null
        & $RedisExe --service-uninstall 2>$null
        Start-Sleep -Seconds 1
    }
}
catch {
    # no existing service
}

Write-Host "Installing Redis service using executable: $RedisExe and config: $RedisConf"
& $RedisExe --service-install $RedisConf
if ($LASTEXITCODE -ne 0) {
    Write-Error "Service installation failed (exit code $LASTEXITCODE)."
    exit 5
}

Write-Host "Starting Redis service..."
& $RedisExe --service-start
Start-Sleep -Seconds 2

try {
    $svc = Get-Service -Name Redis -ErrorAction Stop
    Write-Host "Service 'Redis' status: $($svc.Status)"
}
catch {
    Write-Warning "Could not query service 'Redis'. It may have a different name or installation failed. Check the Windows Event Log for details."
}

Write-Host "Done. Redis should start automatically with Windows. If the service did not start, check the Application/System event log for errors (Event Viewer)."
