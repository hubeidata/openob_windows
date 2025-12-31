<#
Test script to verify OpenOB can use GStreamer via GI.

Usage:
  .\scripts\test_openob_gi.ps1

This script runs a Python test to check GStreamer import.
#>

[CmdletBinding()]
param()

$testCode = @"
import os
import sys

print("PATH:", os.environ.get("PATH", ""))
print("GI_TYPELIB_PATH:", os.environ.get("GI_TYPELIB_PATH", ""))
print("Python:", sys.version)
print("Executable:", sys.executable)

try:
    import gi
    print("gi import OK")
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    print("Gst version:", Gst.version_string())
    print("TEST PASSED")
except Exception as e:
    import traceback
    print("ERROR during import:")
    traceback.print_exc()
    print("TEST FAILED")
    exit(1)
"@

# Get Python executable
$pythonExe = Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $pythonExe) {
    $pythonExe = Get-Command python3 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
}
if (-not $pythonExe) {
    Write-Error "Python not found in PATH."
    exit 2
}

Write-Host "Running GStreamer import test with Python: $pythonExe"
& $pythonExe -c $testCode