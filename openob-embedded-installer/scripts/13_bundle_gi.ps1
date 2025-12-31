[CmdletBinding()]
param(
    [string]$PythonVersion
)

. "$PSScriptRoot\_lib.ps1"

$versions = Read-VersionsJson
if (-not $PythonVersion) {
    $PythonVersion = $versions.python.version
}

$repoRoot = Get-RepoRoot
$installerRoot = Get-InstallerRoot
$runtimeRoot = Get-RuntimeRoot
$pyRoot = Join-Path $runtimeRoot 'python'

if (-not (Test-Path $pyRoot)) {
    throw "Embedded python folder not found. Build step 10 must run first. Expected: $pyRoot"
}

function Get-MajorMinor {
    param([string]$Version)
    $parts = $Version.Split('.')
    if ($parts.Length -lt 2) { return $null }
    return "{0}.{1}" -f $parts[0], $parts[1]
}

$majorMinor = Get-MajorMinor -Version $PythonVersion
if (-not $majorMinor) {
    throw "Could not parse PythonVersion: $PythonVersion"
}

# Example: 3.12 => cp312
$cpTag = "cp{0}{1}" -f $majorMinor.Split('.')[0], $majorMinor.Split('.')[1]

# We need a GTK3_Gvsbuild zip that contains gi built for the same CPython ABI tag.
# The currently present 2025.10.0 zip in this repo is cp314-only; for cp312 we use 2024.10.0.
$gvsbuildVersion = '2024.10.0'

$dlDir = Join-Path $installerRoot '.downloads'
New-Item -ItemType Directory -Force -Path $dlDir | Out-Null

function Test-ZipContainsGiAbi {
    param(
        [string]$Zip,
        [string]$CpTag
    )

    if (-not (Test-Path $Zip)) { return $false }
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $z = [System.IO.Compression.ZipFile]::OpenRead($Zip)
        try {
            $needle = "lib/site-packages/gi/_gi.$CpTag-win_amd64.pyd"
            foreach ($e in $z.Entries) {
                if ($e.FullName -eq $needle) { return $true }
            }
            return $false
        } finally {
            $z.Dispose()
        }
    } catch {
        return $false
    }
}

# Prefer any local gvsbuild zip that contains the correct ABI.
$zipPath = $null
$depDir = Join-Path $repoRoot 'dependencias'
if (Test-Path $depDir) {
    $localZips = Get-ChildItem -Path $depDir -File -Filter 'GTK3_Gvsbuild_*_x64.zip' -ErrorAction SilentlyContinue
    foreach ($lz in $localZips) {
        if (Test-ZipContainsGiAbi -Zip $lz.FullName -CpTag $cpTag) {
            $zipPath = $lz.FullName
            break
        }
    }
}

# Otherwise, download a known-good release for Python 3.12 (cp312).
if (-not $zipPath) {
    $zipPath = Join-Path $dlDir ("GTK3_Gvsbuild_{0}_x64.zip" -f $gvsbuildVersion)
}

$zipUrl = "https://github.com/wingtk/gvsbuild/releases/download/{0}/GTK3_Gvsbuild_{0}_x64.zip" -f $gvsbuildVersion

if (-not (Test-Path $zipPath)) {
    Write-Host "Downloading: $zipUrl"
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath
}

$tempDir = Join-Path $dlDir ("_gvsbuild_extract_{0}_{1}" -f $gvsbuildVersion, $cpTag)
if (Test-Path $tempDir) { Remove-Item -Recurse -Force $tempDir }
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

Write-Host "Extracting: $zipPath -> $tempDir"
Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force

$srcSite = Join-Path $tempDir 'lib\site-packages'
if (-not (Test-Path $srcSite)) {
    throw "Expected site-packages not found inside gvsbuild zip. Expected: $srcSite"
}

$srcGi = Join-Path $srcSite 'gi'
if (-not (Test-Path $srcGi)) {
    throw "Expected gi package not found inside gvsbuild zip. Expected: $srcGi"
}

$expectedPyd = Get-ChildItem -Path $srcGi -File -Filter "_gi.$cpTag-win_amd64.pyd" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $expectedPyd) {
    throw "The provided gvsbuild zip does not contain a gi binary for $cpTag. You likely have a cp314-only zip. Expected something like: $srcGi\\_gi.$cpTag-win_amd64.pyd"
}

$dstSite = Join-Path $pyRoot 'Lib\site-packages'
if (-not (Test-Path $dstSite)) {
    New-Item -ItemType Directory -Force -Path $dstSite | Out-Null
}

$dstGi = Join-Path $dstSite 'gi'
Write-Host "Bundling gi into embedded runtime: $srcGi -> $dstGi"
if (Test-Path $dstGi) { Remove-Item -Recurse -Force $dstGi }
Copy-Item -Recurse -Force $srcGi $dstGi

# Copy required native DLLs so the gi extension module can load.
# These live under gvsbuild's bin/ and must be reachable via PATH at runtime.
$srcBin = Join-Path $tempDir 'bin'
if (-not (Test-Path $srcBin)) {
    throw "Expected bin folder not found inside gvsbuild zip. Expected: $srcBin"
}

$dstNativeRoot = Join-Path $runtimeRoot 'gvsbuild'
$dstBin = Join-Path $dstNativeRoot 'bin'
New-Item -ItemType Directory -Force -Path $dstBin | Out-Null

$dlls = Get-ChildItem -Path $srcBin -File -Filter '*.dll' -ErrorAction SilentlyContinue
if (-not $dlls -or $dlls.Count -eq 0) {
    throw "No DLLs found in gvsbuild bin folder. Expected native deps under: $srcBin"
}

Write-Host "Bundling gvsbuild native DLLs: $srcBin -> $dstBin"
Copy-Item -Force $dlls.FullName $dstBin

# Also copy dist-info for introspection/metadata (optional but helpful)
$distInfo = Get-ChildItem -Path $srcSite -Directory -Filter 'PyGObject*.dist-info' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($distInfo) {
    $dst = Join-Path $dstSite $distInfo.Name
    Write-Host "Copying dist-info: $($distInfo.FullName) -> $dst"
    if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
    Copy-Item -Recurse -Force $distInfo.FullName $dst
}

# Ensure a minimal sitecustomize.py is present to add DLL search dirs and GI_TYPELIB_PATH at runtime
$siteCustomizePath = Join-Path $dstSite 'sitecustomize.py'
if (-not (Test-Path $siteCustomizePath)) {
    Write-Host "Adding sitecustomize.py to runtime site-packages: $siteCustomizePath"
    $siteCustomizeContent = @'
import os
from pathlib import Path
import sys

def add_if_exists(path):
    p = Path(path)
    if p.is_dir():
        try:
            os.add_dll_directory(str(p))
            # minimal diagnostic only if env var OPENOB_DEBUG_GI set
            if os.environ.get('OPENOB_DEBUG_GI'):
                print(f"[openob-site] added dll dir: {p}")
            return True
        except Exception:
            return False
    return False

python_dir = Path(sys.executable).parent
runtime_root = python_dir.parent
# gvsbuild native bin relative to runtime root
gvsbuild_bin = runtime_root / 'gvsbuild' / 'bin'
add_if_exists(gvsbuild_bin)
# also try system GStreamer bin
system_gst_bin = Path(r"C:\Program Files\gstreamer\1.0\msvc_x86_64\bin")
add_if_exists(system_gst_bin)
# set GI_TYPELIB_PATH if not present and system girepo exists
if 'GI_TYPELIB_PATH' not in os.environ:
    girepo = Path(r"C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0")
    if girepo.is_dir():
        os.environ['GI_TYPELIB_PATH'] = str(girepo)
        if os.environ.get('OPENOB_DEBUG_GI'):
            print(f"[openob-site] set GI_TYPELIB_PATH={girepo}")
'@
    Set-Content -Path $siteCustomizePath -Value $siteCustomizeContent -Encoding UTF8
}

Write-Host "gi bundled (ABI tag $cpTag)."
