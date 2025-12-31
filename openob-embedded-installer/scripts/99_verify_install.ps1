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
# Load gstreamer env values (if present) and expand relative paths to runtime root
$gstEnv = Join-Path $runtimeRoot 'config\gstreamer.env'
if (Test-Path $gstEnv) {
    Get-Content $gstEnv | Where-Object { $_ -and -not $_.TrimStart().StartsWith('#') } | ForEach-Object {
        $parts = $_ -split '=',2
        if ($parts.Length -eq 2) {
            $name = $parts[0].Trim()
            $value = $parts[1].Trim()
            if ($value.StartsWith('.\')) { $value = Join-Path $runtimeRoot $value.Substring(2) }
            # If the referenced path does not exist, warn and skip setting the env var (prevents stale config)
            if ($value -and ($value -match '[\\/]') -and -not (Test-Path $value)) {
                Write-Warning "GStreamer config referenced path does not exist: $value; skipping setting env $name"
            }
            else {
                Write-Host "Setting env $name = $value"
                # Set environment variable for process safely (dynamic name)
                Set-Item -Path ("Env:{0}" -f $name) -Value $value
            }
        }
    }
}
# If GstBin was set, add it to PATH and set GST_PLUGIN_PATH as well
if ($env:GstBin) {
    Write-Host "Prepending GstBin to PATH: $env:GstBin"
    $env:PATH = "$env:GstBin;$env:PATH"
    if (-not $env:GST_PLUGIN_PATH -or $env:GST_PLUGIN_PATH -eq '') {
        $env:GST_PLUGIN_PATH = $env:GstBin
    }
}
$gvsBin = Join-Path $runtimeRoot 'gvsbuild\bin'
if (Test-Path $gvsBin) {
    $env:PATH = "$gvsBin;$env:PATH"
}
& $pyExe -c "import sys; print(sys.version)"
& $pyExe -c "import openob; print('openob import OK')"
& $pyExe -c "import gi; gi.require_version('Gst','1.0'); from gi.repository import Gst; Gst.init(None); print('gi Gst OK')"

if ($CheckRedis) {
    Write-Host 'Checking Redis connectivity (127.0.0.1:6379)...'
    $t = Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -WarningAction SilentlyContinue
    if (-not $t.TcpTestSucceeded) {
        throw 'Redis not reachable on 127.0.0.1:6379'
    }
    Write-Host 'Redis reachable.'
}

Write-Host 'Verify OK.'
