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
$pthFile = Get-ChildItem -Path $pyRoot -Filter 'python*._pth' -ErrorAction SilentlyContinue | Select-Object -First 1
$pthPath = $null
if ($pthFile) {
    $pthPath = $pthFile.FullName
}

if (-not (Test-Path $pyRoot)) {
    throw "Embedded python folder not found. Build step 10 must run first. Expected: $pyRoot"
}

# Download the official Python Windows installer (contains Tcl/Tk + tkinter)
$dlDir = Join-Path $installerRoot '.downloads'
New-Item -ItemType Directory -Force -Path $dlDir | Out-Null

$installerExe = Join-Path $dlDir ("python-{0}-amd64.exe" -f $PythonVersion)
$installerUrl = "https://www.python.org/ftp/python/{0}/python-{0}-amd64.exe" -f $PythonVersion

if (-not (Test-Path $installerExe)) {
    Write-Host "Downloading: $installerUrl"
    Invoke-WebRequest -Uri $installerUrl -OutFile $installerExe
}

function Resolve-FullPythonRootFromInstallPath {
    param([string]$InstallPath)
    if (-not $InstallPath) { return $null }
    $p = $InstallPath.TrimEnd('\\')
    if (Test-Path (Join-Path $p 'DLLs')) { return $p }
    return $null
}

function Get-FullPythonInstallPathFromRegistry {
    param([string]$MajorMinor)

    $regCandidates = @(
        "HKCU:\\Software\\Python\\PythonCore\\$MajorMinor\\InstallPath",
        "HKLM:\\SOFTWARE\\Python\\PythonCore\\$MajorMinor\\InstallPath",
        "HKLM:\\SOFTWARE\\WOW6432Node\\Python\\PythonCore\\$MajorMinor\\InstallPath"
    )

    foreach ($k in $regCandidates) {
        try {
            $v = (Get-ItemProperty -Path $k -ErrorAction Stop).'(default)'
            if ($v) { return $v }
        } catch {
            # ignore
        }
    }
    return $null
}

function Get-MajorMinor {
    param([string]$Version)
    $parts = $Version.Split('.')
    if ($parts.Length -lt 2) { return $null }
    return "{0}.{1}" -f $parts[0], $parts[1]
}

$majorMinor = Get-MajorMinor -Version $PythonVersion
$fullInstallPath = Get-FullPythonInstallPathFromRegistry -MajorMinor $majorMinor
$fullRoot = Resolve-FullPythonRootFromInstallPath -InstallPath $fullInstallPath

if (-not $fullRoot) {
    Write-Host "Full Python not found in registry; installing Python $PythonVersion to fetch Tcl/Tk..."
    $installArgs = @(
        '/quiet',
        'InstallAllUsers=0',
        'PrependPath=0',
        'Include_launcher=0',
        'Shortcuts=0',
        'Include_test=0',
        'Include_doc=0',
        'Include_pip=0',
        'Include_tcltk=1'
    )

    $proc = Start-Process -FilePath $installerExe -ArgumentList $installArgs -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        throw "Python installer failed with exit code $($proc.ExitCode)"
    }

    $fullInstallPath = Get-FullPythonInstallPathFromRegistry -MajorMinor $majorMinor
    $fullRoot = Resolve-FullPythonRootFromInstallPath -InstallPath $fullInstallPath
}

if (-not $fullRoot) {
    throw "Could not locate a full Python install for $PythonVersion after installation attempt."
}

Write-Host "Using full Python install at: $fullRoot"

# Copy Tcl/Tk runtime bits into embedded python
$srcTcl = Join-Path $fullRoot 'tcl'
$dstTcl = Join-Path $pyRoot 'tcl'
if (-not (Test-Path $srcTcl)) {
    throw "Expected Tcl folder not found in full install: $srcTcl"
}

Write-Host "Copying Tcl folder: $srcTcl -> $dstTcl"
if (Test-Path $dstTcl) { Remove-Item -Recurse -Force $dstTcl }
Copy-Item -Recurse -Force $srcTcl $dstTcl

# DLLs / extension module
# NOTE: Tcl/Tk binaries depend on additional DLLs that live under the full install's DLLs folder
# (e.g. zlib1.dll, libffi, OpenSSL). If we don't copy them, importing _tkinter will fail with
# "DLL load failed" / "module not found".
$srcDlls = Join-Path $fullRoot 'DLLs'
$needFiles = @(
    '_tkinter.pyd',
    'tcl86t.dll',
    'tk86t.dll',
    'zlib1.dll',
    'libffi-8.dll',
    'libcrypto-3.dll',
    'libssl-3.dll'
)
foreach ($f in $needFiles) {
    $src = Join-Path $srcDlls $f
    if (-not (Test-Path $src)) {
        throw "Required file missing in full Python install: $src"
    }
    $dst = Join-Path $pyRoot $f
    Copy-Item -Force $src $dst
}

# Pure-Python tkinter package
$srcTkinter = Join-Path $fullRoot 'Lib\\tkinter'
$dstLib = Join-Path $pyRoot 'Lib'
$dstTkinter = Join-Path $dstLib 'tkinter'

if (-not (Test-Path $srcTkinter)) {
    throw "Expected tkinter package not found: $srcTkinter"
}

if (-not (Test-Path $dstLib)) {
    New-Item -ItemType Directory -Force -Path $dstLib | Out-Null
}

Write-Host "Copying tkinter package: $srcTkinter -> $dstTkinter"
if (Test-Path $dstTkinter) { Remove-Item -Recurse -Force $dstTkinter }
Copy-Item -Recurse -Force $srcTkinter $dstTkinter

# Ensure Lib is on sys.path for embeddable runtime
if ($pthPath -and (Test-Path $pthPath)) {
    $lines = Get-Content -Path $pthPath -ErrorAction Stop
    $hasLib = $false
    foreach ($ln in $lines) {
        if ($ln.Trim() -ieq 'Lib') { $hasLib = $true; break }
    }

    if (-not $hasLib) {
        Write-Host "Adding 'Lib' to embeddable ._pth: $pthPath"
        # Insert Lib just before Lib\site-packages if present; otherwise append
        $out = New-Object System.Collections.Generic.List[string]
        $inserted = $false
        foreach ($ln in $lines) {
            if (-not $inserted -and $ln.Trim() -ieq 'Lib\site-packages') {
                $out.Add('Lib')
                $inserted = $true
            }
            $out.Add($ln)
        }
        if (-not $inserted) { $out.Add('Lib') }
        Set-Content -Path $pthPath -Value $out -Encoding ASCII
    }
} else {
    Write-Host "WARNING: python*._pth not found (skipping Lib path injection) under: $pyRoot"
}

Write-Host 'Tkinter bundled into embedded runtime.'
