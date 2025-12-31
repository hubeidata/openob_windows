<#
Test script to verify OpenOB can use GStreamer via GI.

Usage:
  .\scripts\test_openob_gi.ps1

This script runs a Python test to check GStreamer import.
#>

[CmdletBinding()]
param(
    [switch]$InstallDeps,
    [switch]$Yes
)

$testCode = @'
import os
import sys

print("PATH:", os.environ.get("PATH", ""))
print("GI_TYPELIB_PATH:", os.environ.get("GI_TYPELIB_PATH", ""))
print("Python:", sys.version)
print("Executable:", sys.executable)

try:
    import typing_extensions
except Exception:
    print("ERROR: Required package 'typing_extensions' not found.")
    print("Install it with: python -m pip install typing_extensions")
    print("TEST FAILED (missing dependency)")
    import sys
    sys.exit(2)

try:
    import gi
    print("gi import OK")
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    # Ensure GStreamer is initialized before calling version_string
    try:
        Gst.init(None)
    except Exception as e:
        # Some GStreamer builds may not require explicit init, but report it for debugging
        print("WARNING: Gst.init() raised:", e)
    try:
        print("Gst version:", Gst.version_string())
        print("TEST PASSED")
    except Exception as e:
        print("ERROR getting Gst.version_string():", e)
        raise
except Exception as e:
    import traceback
    print("ERROR during import:")
    traceback.print_exc()
    print("TEST FAILED")
    sys.exit(1)
'@

# Get Python executable
$pythonExe = Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $pythonExe) {
    $pythonExe = Get-Command python3 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
}
if (-not $pythonExe) {
    Write-Error "Python not found in PATH."
    exit 2
}

# If requested, attempt to install missing Python dependencies using pip
if ($InstallDeps) {
    if (-not $Yes) {
        $resp = Read-Host "Instalar dependencias en '$pythonExe'? (y/N)"
        if ($resp -notin @('y','Y','s','S')) {
            Write-Host "Cancelado por el usuario.";
            exit 0
        }
    }
    Write-Host "Actualizando pip y instalando 'typing_extensions' en: $pythonExe"
    & $pythonExe -m pip install --upgrade pip
    $pipExit = $LASTEXITCODE
    if ($pipExit -ne 0) {
        Write-Error "Fallo al actualizar pip (exit $pipExit)."
        exit 4
    }
    & $pythonExe -m pip install typing_extensions
    $pipExit = $LASTEXITCODE
    if ($pipExit -ne 0) {
        Write-Error "Fallo al instalar 'typing_extensions' (exit $pipExit). Intenta instalar manualmente: $pythonExe -m pip install typing_extensions"
        exit 5
    }
    Write-Host "'typing_extensions' instalado correctamente."
}

# Write test code to a temporary file to avoid quoting/expansion issues and run it
$tempFile = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "test_openob_gi_{0}.py" -f ([System.Guid]::NewGuid().ToString()))
Set-Content -Path $tempFile -Value $testCode -Encoding UTF8
try {
    Write-Host "Running GStreamer import test with Python: $pythonExe (temp file: $tempFile)"
    & $pythonExe $tempFile
    $exitCode = $LASTEXITCODE
} finally {
    Remove-Item -Path $tempFile -Force -ErrorAction SilentlyContinue
}

if ($exitCode -eq 2) {
    Write-Host "Dependency missing: 'typing_extensions'. Instale con: `"$pythonExe -m pip install typing_extensions`""
    Write-Host "(Para instalar automáticamente, ejecute: `".\scripts\test_openob_gi.ps1 -InstallDeps -Yes`")"
}
if (-not $exitCode) { $exitCode = 0 }
exit $exitCode