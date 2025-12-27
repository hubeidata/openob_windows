[CmdletBinding()]
param(
    [switch]$CheckRedis
)

. "$PSScriptRoot\_lib.ps1"

$pyExe = Get-EmbeddedPythonExe
if (-not (Test-Path $pyExe)) {
    throw "Embedded python not found. Build runtime first. Expected: $pyExe"
}

Write-Host 'Verifying embedded runtime imports...'
$runtimeRoot = Get-RuntimeRoot
$gvsBin = Join-Path $runtimeRoot 'gvsbuild\bin'
if (Test-Path $gvsBin) {
    $env:PATH = "$gvsBin;$env:PATH"
}
& $pyExe -c "import sys; print(sys.version)"
& $pyExe -c "import openob; print('openob import OK')"
& $pyExe -c "import gi; print('gi import OK')"

if ($CheckRedis) {
    Write-Host 'Checking Redis connectivity (127.0.0.1:6379)...'
    $t = Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -WarningAction SilentlyContinue
    if (-not $t.TcpTestSucceeded) {
        throw 'Redis not reachable on 127.0.0.1:6379'
    }
    Write-Host 'Redis reachable.'
}

Write-Host 'Verify OK.'
