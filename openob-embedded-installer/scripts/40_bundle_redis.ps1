[CmdletBinding()]
param(
    [switch]$Skip
)

. "$PSScriptRoot\_lib.ps1"

if ($Skip) {
    Write-Host 'Skipping Redis bundling.'
    exit 0
}

# Prevent accidental bundling: only bundle Redis when explicitly allowed by env var.
if (-not $env:ALLOW_BUNDLE_REDIS) {
    Write-Host 'Redis bundling is disabled by default (external install).'
    Write-Host 'To enable bundling for local/test builds set environment variable: $env:ALLOW_BUNDLE_REDIS=1'
    exit 0
}

$repoRoot = Get-RepoRoot
$srcRedis = Join-Path $repoRoot 'redis-server'
if (-not (Test-Path (Join-Path $srcRedis 'redis-server.exe'))) {
    throw "redis-server.exe not found at $srcRedis"
}

$runtimeRoot = Get-RuntimeRoot
$destRedis = Join-Path $runtimeRoot 'redis'

Write-Host "Copying Redis: $srcRedis -> $destRedis"
if (Test-Path $destRedis) {
    Remove-Item -Recurse -Force $destRedis
}
Copy-Item -Recurse -Force $srcRedis $destRedis

Write-Host 'Redis bundled.'
