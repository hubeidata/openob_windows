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

& "$PSScriptRoot\00_check_prereqs.ps1"
& "$PSScriptRoot\10_fetch_python_embedded.ps1" -PythonVersion $PythonVersion
if (-not $SkipTkBundle) {
    & "$PSScriptRoot\12_bundle_tkinter.ps1" -PythonVersion $PythonVersion
}
if (-not $SkipGiBundle) {
    & "$PSScriptRoot\13_bundle_gi.ps1" -PythonVersion $PythonVersion
}
& "$PSScriptRoot\20_install_runtime_deps.ps1"
& "$PSScriptRoot\30_install_openob.ps1" -NoDeps
if (-not $SkipUiBundle) {
    & "$PSScriptRoot\35_bundle_ui.ps1"
}
if (-not $SkipRedisBundle) {
    & "$PSScriptRoot\40_bundle_redis.ps1"
}
& "$PSScriptRoot\99_verify_install.ps1"

Write-Host 'All steps completed.'
