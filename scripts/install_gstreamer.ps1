<#
Install GStreamer from MSI and add paths to system PATH permanently.

Usage (Run PowerShell as Administrator):
  .\scripts\install_gstreamer.ps1

This script installs GStreamer from the MSI file in manual\gstreamer\, adds the bin path to system PATH, and runs tests.
#>

[CmdletBinding()]
param()

function Assert-Admin {
    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-Error "This script must be run as Administrator. Open an elevated PowerShell and re-run."
        exit 2
    }
}

Assert-Admin

$repoRoot = Split-Path -Parent $PSScriptRoot
$msiPath = Join-Path $repoRoot 'gstreamer\gstreamer-1.0-msvc-x86_64-1.26.10.msi'

if (-not (Test-Path $msiPath)) {
    Write-Error "GStreamer MSI not found at: $msiPath"
    exit 3
}

Write-Host "Installing GStreamer from: $msiPath"
$logPath = Join-Path $repoRoot 'install_gstreamer.log'
$process = Start-Process -FilePath 'msiexec.exe' -ArgumentList "/i `"$msiPath`" /quiet /norestart /l*v `"$logPath`"" -Wait -PassThru
if ($process.ExitCode -ne 0) {
    Write-Error "MSI installation failed with exit code $($process.ExitCode). Check log: $logPath"
    exit 5
}
Write-Host "Installation completed. Log: $logPath"

# Detect GStreamer install path
$gstInstallDir = Get-ChildItem -Path 'C:\Program Files' -Recurse -Directory | Where-Object { $_.Name -eq 'msvc_x86_64' -and (Test-Path (Join-Path $_.FullName 'bin')) } | Select-Object -First 1
if (-not $gstInstallDir) {
    # Try Program Files (x86) for 32-bit
    $gstInstallDir = Get-ChildItem -Path 'C:\Program Files (x86)' -Recurse -Directory | Where-Object { $_.Name -eq 'msvc_x86_64' -and (Test-Path (Join-Path $_.FullName 'bin')) } | Select-Object -First 1
}
if (-not $gstInstallDir) {
    Write-Error "Could not find GStreamer installation directory with bin folder."
    exit 6
}
$gstRoot = $gstInstallDir.FullName
Write-Host "Detected GStreamer root at: $gstRoot"

$gstBinPath = Join-Path $gstRoot 'bin'
$gstLibPath = Join-Path $gstRoot 'lib'
$gstGiPath = Join-Path $gstLibPath 'girepository-1.0'
$gstPluginPath = Join-Path $gstLibPath 'gstreamer-1.0'
$gstPySitePath = Join-Path $gstLibPath 'site-packages'

if (-not (Test-Path $gstBinPath)) {
    Write-Warning "GStreamer bin path not found at: $gstBinPath. Installation may have failed."
    exit 4
}

# Add bin to system PATH permanently
$currentPath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
if ($currentPath -notlike "*$gstBinPath*") {
    $newPath = "$currentPath;$gstBinPath"
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'Machine')
    Write-Host "Added $gstBinPath to system PATH."
} else {
    Write-Host "$gstBinPath already in system PATH."
}

# Set GI_TYPELIB_PATH
$currentGiPath = [Environment]::GetEnvironmentVariable('GI_TYPELIB_PATH', 'Machine')
if ($currentGiPath -notlike "*$gstGiPath*") {
    $newGiPath = if ($currentGiPath) { "$currentGiPath;$gstGiPath" } else { $gstGiPath }
    [Environment]::SetEnvironmentVariable('GI_TYPELIB_PATH', $newGiPath, 'Machine')
    Write-Host "Set GI_TYPELIB_PATH to include $gstGiPath."
}

# Set GST_PLUGIN_PATH
$currentGstPath = [Environment]::GetEnvironmentVariable('GST_PLUGIN_PATH', 'Machine')
if ($currentGstPath -notlike "*$gstPluginPath*") {
    $newGstPath = if ($currentGstPath) { "$currentGstPath;$gstPluginPath" } else { $gstPluginPath }
    [Environment]::SetEnvironmentVariable('GST_PLUGIN_PATH', $newGstPath, 'Machine')
    Write-Host "Set GST_PLUGIN_PATH to include $gstPluginPath."
}

# Set PYTHONPATH for site-packages
$currentPyPath = [Environment]::GetEnvironmentVariable('PYTHONPATH', 'Machine')
if ($currentPyPath -notlike "*$gstPySitePath*") {
    $newPyPath = if ($currentPyPath) { "$currentPyPath;$gstPySitePath" } else { $gstPySitePath }
    [Environment]::SetEnvironmentVariable('PYTHONPATH', $newPyPath, 'Machine')
    Write-Host "Set PYTHONPATH to include $gstPySitePath."
}

Write-Host "GStreamer installation completed."

# Run tests
Write-Host "Running tests..."
& "$PSScriptRoot\test_openob_gi.ps1"