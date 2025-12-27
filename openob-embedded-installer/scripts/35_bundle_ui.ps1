[CmdletBinding()]
param()

. "$PSScriptRoot\_lib.ps1"

$repoRoot = Get-RepoRoot
$runtimeRoot = Get-RuntimeRoot

$srcUi = Join-Path $repoRoot 'ui'
$dstUi = Join-Path $runtimeRoot 'ui'

if (-not (Test-Path $srcUi)) {
    throw "UI folder not found at: $srcUi"
}

Write-Host "Bundling UI: $srcUi -> $dstUi"

if (Test-Path $dstUi) {
    Remove-Item -Recurse -Force $dstUi
}

Copy-Item -Recurse -Force $srcUi $dstUi

# Remove caches to keep payload smaller/cleaner
Get-ChildItem -Path $dstUi -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue
}

Write-Host 'UI bundled.'
