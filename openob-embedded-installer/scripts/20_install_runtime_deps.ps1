[CmdletBinding()]
param(
    [string]$RequirementsPath
)

. "$PSScriptRoot\_lib.ps1"

$pyExe = Get-EmbeddedPythonExe
if (-not (Test-Path $pyExe)) {
    throw "Embedded python not found. Run 10_fetch_python_embedded.ps1 first. Expected: $pyExe"
}

$installerRoot = Get-InstallerRoot
if (-not $RequirementsPath) {
    $RequirementsPath = Join-Path $installerRoot 'installer\config\requirements_runtime.txt'
}
if (-not (Test-Path $RequirementsPath)) {
    throw "Requirements file not found: $RequirementsPath"
}

$downloadsDir = Join-Path $installerRoot '.downloads'
Ensure-Directory $downloadsDir
$getPipPath = Join-Path $downloadsDir 'get-pip.py'
Invoke-Download -Url 'https://bootstrap.pypa.io/get-pip.py' -OutFile $getPipPath

Write-Host 'Installing pip into embedded Python...'
& $pyExe $getPipPath

Write-Host 'Upgrading pip tooling...'
& $pyExe -m pip install --upgrade pip setuptools wheel

Write-Host "Installing runtime requirements from $RequirementsPath"
& $pyExe -m pip install -r $RequirementsPath
