<#
Uninstall the Redis Windows service installed by install_redis_service.ps1.

Usage (Run PowerShell as Administrator):
  .\scripts\uninstall_redis_service.ps1

This will stop the service and uninstall it.
#>

[CmdletBinding()]
param(
    [string]$RedisExe = '.\redis-server\redis-server.exe'
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

Write-Host "Stopping Redis service (if exists)..."
try { Get-Service -Name Redis -ErrorAction Stop | Stop-Service -Force -ErrorAction SilentlyContinue } catch {}
Start-Sleep -Seconds 1

Write-Host "Uninstalling Redis service..."
& $RedisExe --service-stop 2>$null
& $RedisExe --service-uninstall
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Service uninstall may have failed or service did not exist. Exit code: $LASTEXITCODE"
}
else {
    Write-Host "Service uninstalled."
}
