[CmdletBinding()]
param()

. "$PSScriptRoot\_lib.ps1"

Write-Host "Repo root: $(Get-RepoRoot)"
Write-Host "Installer root: $(Get-InstallerRoot)"
Write-Host "Runtime root: $(Get-RuntimeRoot)"

# PowerShell version
if ($PSVersionTable.PSVersion.Major -lt 5) {
    throw "PowerShell 5.1+ required"
}

# Check basic networking cmdlets
Assert-Command 'Invoke-WebRequest'

# Check OpenOB sources exist
$repoRoot = Get-RepoRoot
$openobDir = Join-Path $repoRoot 'openob'
if (-not (Test-Path (Join-Path $openobDir 'setup.py'))) {
    throw "OpenOB project not found at $openobDir"
}

Write-Host 'Prereqs OK.'
