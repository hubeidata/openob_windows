[CmdletBinding()]
param(
    [switch]$NoDeps
)

. "$PSScriptRoot\_lib.ps1"

$pyExe = Get-EmbeddedPythonExe
if (-not (Test-Path $pyExe)) {
    throw "Embedded python not found. Run 10_fetch_python_embedded.ps1 first. Expected: $pyExe"
}

$repoRoot = Get-RepoRoot
$openobProject = Join-Path $repoRoot 'openob'
if (-not (Test-Path (Join-Path $openobProject 'setup.py'))) {
    throw "OpenOB setup.py not found at $openobProject"
}

Write-Host "Installing OpenOB from: $openobProject"
if ($NoDeps) {
    & $pyExe -m pip install --no-deps $openobProject
} else {
    & $pyExe -m pip install $openobProject
}
