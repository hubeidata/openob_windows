[CmdletBinding()]
param(
    [switch]$SkipRedisBundle,
    [switch]$SkipUiBundle,
    [switch]$SkipTkBundle,
    [switch]$SkipGiBundle,
    [string]$PythonVersion
)

. "$PSScriptRoot\_lib.ps1"

Write-Host '== OpenOB embedded installer: build_all =='

# Ensure GStreamer and Redis are NOT bundled into the installer by default.
# Remove any existing bundled runtime folders so the produced installer does not contain
# GStreamer or Redis (these are expected to be installed externally by the user).
$runtimeRoot = Get-RuntimeRoot
$forbidden = @( 'gstreamer', 'redis' )
foreach ($d in $forbidden) {
    $p = Join-Path $runtimeRoot $d
    if (Test-Path $p) {
        Write-Host "Removing bundled runtime folder to keep installer clean: $p"
        Remove-Item -Recurse -Force $p
    }
}
# Remove stale GStreamer env config file if present (left over from older builds that bundled GStreamer)
$configGst = Join-Path (Join-Path $runtimeRoot 'config') 'gstreamer.env'
if (Test-Path $configGst) {
    Write-Host "Removing stale GStreamer config: $configGst"
    Remove-Item -Force $configGst
}

# Clear any process environment variables that might reference GStreamer from previous runs
$envVarsToClear = 'GstBin','GI_TYPELIB_PATH','GST_PLUGIN_PATH','GstPySitePackages'
foreach ($v in $envVarsToClear) {
    if (Test-Path ("Env:$v")) {
        Remove-Item ("Env:$v") -ErrorAction SilentlyContinue
        Write-Host "Cleared env $v"
    }
}

& "$PSScriptRoot\00_check_prereqs.ps1"
& "$PSScriptRoot\10_fetch_python_embedded.ps1" -PythonVersion $PythonVersion
if (-not $SkipTkBundle) {
    & "$PSScriptRoot\12_bundle_tkinter.ps1" -PythonVersion $PythonVersion
}
if (-not $SkipGiBundle) {
    & "$PSScriptRoot\13_bundle_gi.ps1" -PythonVersion $PythonVersion
}
# Bundle GStreamer if present in packaging
# & "$PSScriptRoot\42_bundle_gstreamer.ps1"
& "$PSScriptRoot\20_install_runtime_deps.ps1"
& "$PSScriptRoot\30_install_openob.ps1" -NoDeps
if (-not $SkipUiBundle) {
    & "$PSScriptRoot\35_bundle_ui.ps1"
}
# if (-not $SkipRedisBundle) {
#     & "$PSScriptRoot\40_bundle_redis.ps1"
# }
& "$PSScriptRoot\99_verify_install.ps1"

Write-Host 'All steps completed.'
