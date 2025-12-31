<#
Comprueba gi/GStreamer en el Python del runtime embebido (o en PATH).

Uso:
  .\scripts\test_embebido.ps1
Salida:
  0 = gi + Gst OK
  1 = Python no encontrado
  2 = gi paquete o _gi.pyd no encontrado
  3 = import/require falla (salida con traceback)
#>
[CmdletBinding()]
param(
    [string]$PythonExe
)

# Detect runtime-embedded Python first (unless -PythonExe is provided)
$repoRoot = Split-Path -Parent $PSScriptRoot
$embedded = Join-Path $repoRoot 'openob-embedded-installer\packaging\openob_runtime\python\python.exe'

if ($PythonExe) {
    if (Test-Path $PythonExe) { $python = $PythonExe }
    else {
        Write-Error "El ejecutable proporcionado en -PythonExe no existe: $PythonExe"
        exit 1
    }
} elseif (Test-Path $embedded) {
    $python = $embedded
} else {
    $python = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
}

if (-not $python) {
    Write-Error "Python no encontrado (ni runtime embebido ni en PATH)."
    Write-Host "Si instalaste OpenOB, prueba: .\scripts\test_embebido.ps1 -PythonExe 'C:\Path\To\installed\python\python.exe'"
    exit 1
}
Write-Host "Usando Python: $python"

# Check for gi package files
$sitePrefix = & $python -c "import sysconfig,sys; print(sysconfig.get_paths()['purelib'])" 2>$null
if (-not $sitePrefix) {
    Write-Warning "No se pudo determinar site-packages. Se intentará import en runtime."
} else {
    $giDir = Join-Path $sitePrefix 'gi'
    $giPyds = Get-ChildItem -Path $sitePrefix -Filter '_gi*.pyd' -ErrorAction SilentlyContinue
    Write-Host "site-packages: $sitePrefix"
    Write-Host "gi dir exists: $([System.IO.Directory]::Exists($giDir))"
    if ($giPyds) {
        Write-Host "_gi binary candidates:"
        $giPyds | ForEach-Object { Write-Host "  $($_.FullName)" }
    } else {
        Write-Warning "_gi*.pyd no encontrado en site-packages."
    }
}

# Run an inline python check to import gi and Gst and print detailed traceback on error
# enhance the check by ensuring native DLL/search paths and GI_TYPELIB_PATH are set from common locations
$gvsbuildBin = Join-Path $repoRoot 'openob-embedded-installer\packaging\openob_runtime\gvsbuild\bin'
$systemGirepo = 'C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0'
$pyCheck = @'
import os,sys,traceback
# prepend gvsbuild/bin to PATH if present (compute relative to python executable)
_python_dir = os.path.dirname(sys.executable)
_gvs = os.path.abspath(os.path.join(_python_dir, '..', 'gvsbuild', 'bin'))
if os.path.isdir(_gvs):
    os.environ['PATH'] = _gvs + os.pathsep + os.environ.get('PATH','')
# set GI_TYPELIB_PATH to system gstreamer girepository if not already set
if not os.environ.get('GI_TYPELIB_PATH'):
    _girepo = r"C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0"
    print('attempting girepo path:', _girepo, os.path.isdir(_girepo))
    if os.path.isdir(_girepo):
        os.environ['GI_TYPELIB_PATH'] = _girepo
# also prepend system gstreamer bin to PATH so gstreamer DLLs can be found
_gstbin = r"C:\Program Files\gstreamer\1.0\msvc_x86_64\bin"
if os.path.isdir(_gstbin):
    os.environ['PATH'] = _gstbin + os.pathsep + os.environ.get('PATH','')
# debug prints
print('PATH contains gvsbuild_bin:', os.path.isdir(_gvs))
print('PATH contains system_gst_bin:', os.path.isdir(_gstbin))
print('GI_TYPELIB_PATH:', os.environ.get('GI_TYPELIB_PATH'))
try:
    import gi
    print("gi import OK; gi.__file__=", getattr(gi, "__file__", "<no file>"))
    gi.require_version("Gst","1.0")
    from gi.repository import Gst
    try:
        Gst.init(None)
    except Exception as e:
        print("Gst.init() warning:", e)
    print("Gst.version_string():", Gst.version_string())
    sys.exit(0)
except Exception as e:
    print("ERROR: import failed:", e)
    traceback.print_exc()
    sys.exit(3)
'@

# Write the inline Python to a temporary file and execute it to avoid quoting issues
$tempFile = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "check_gi_{0}.py" -f ([System.Guid]::NewGuid().ToString()))
Set-Content -Path $tempFile -Value $pyCheck -Encoding UTF8
try {
    Write-Host "`nEjecutando comprobación de import gi/Gst... (archivo temporal: $tempFile)"
    $proc = & $python $tempFile 2>&1
    Write-Host $proc
    $last = $LASTEXITCODE
} finally {
    Remove-Item -Path $tempFile -Force -ErrorAction SilentlyContinue
}
if ($last -eq 0) { Write-Host "`nRESULT: gi + Gst OK"; exit 0 }
else { Write-Error "`nRESULT: fallo en import (exit $last)"; exit $last }