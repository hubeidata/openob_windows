<#
install_openob.ps1

Instala las dependencias locales y prepara el entorno para ejecutar OpenOB en Windows.
Usa los instaladores y paquetes encontrados en la carpeta `dependencias` dentro del repo.

Pasos que realiza (solo los pasos válidos y con comprobaciones):
 - Requiere ejecutar PowerShell elevado (instalación de MSI y servicios).
 - Instala Python 3.12 si no existe o si la versión es distinta.
 - Instala GStreamer runtime (MSI) y SDK/devel (si están disponibles).
 - Instala Redis MSI (si está disponible) y arranca el servicio Redis.
 - Crea un virtualenv en `.venv` usando el Python instalado.
 - Actualiza pip y instala ruedas/paquetes locales (gvsbuild wheels si aparecen).
 - Instala `redis<4.0,>=3.5.3` en el venv y el paquete local de OpenOB.
 - Crea `.venv\Lib\site-packages\gstreamer.pth` apuntando al site-packages de GStreamer si se detecta la instalación.

Este script asume que todos los instaladores necesarios están en `..\dependencias` relativo a este script.
Solo ejecuta pasos cuando los ficheros correspondientes existen.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-Admin {
    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-Error 'This script must be run as Administrator. Re-run PowerShell as Administrator and try again.'
        exit 1
    }
}

function Run-Msi([string]$msiPath) {
    if (-not (Test-Path $msiPath)) { return $false }
    Write-Host "Installing MSI: $msiPath"
    $args = "/i `"$msiPath`" /qn /norestart"
    $p = Start-Process -FilePath msiexec.exe -ArgumentList $args -Wait -Passthru
    return ($p.ExitCode -eq 0)
}

function Run-Exe([string]$exePath, [string[]]$arguments) {
    if (-not (Test-Path $exePath)) { return $false }
    Write-Host "Running: $exePath $($arguments -join ' ')"
    $p = Start-Process -FilePath $exePath -ArgumentList $arguments -Wait -Passthru
    return ($p.ExitCode -eq 0)
}

Assert-Admin

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir '..')).Path
$Deps = Join-Path $RepoRoot 'dependencias'

Write-Host "Repo root: $RepoRoot"
Write-Host "Dependencies folder: $Deps"

# 1) Install Python if missing or wrong version
$pythonCmd = (Get-Command python -ErrorAction SilentlyContinue).Source
$needPythonInstall = $true
if ($pythonCmd) {
    try {
        $ver = & $pythonCmd -c "import sys; print('.'.join(map(str,sys.version_info[:2])))" 2>$null
        if ($ver -match '^3\.(\d+)$') {
            $minor = [int]$Matches[1]
            if ($minor -ge 12) { $needPythonInstall = $false }
        }
    } catch {
        $needPythonInstall = $true
    }
}

$pythonInstaller = Join-Path $Deps 'python-3.12.0-amd64.exe'
if ($needPythonInstall) {
    if (Test-Path $pythonInstaller) {
        Write-Host 'Installing Python 3.12 (silent)...'
        $args = '/quiet','InstallAllUsers=1','PrependPath=1'
        Start-Process -FilePath $pythonInstaller -ArgumentList $args -Wait -NoNewWindow -Passthru | Out-Null
        Write-Host 'Python installer finished.'
        # refresh pythonCmd
        $pythonCmd = (Get-Command python -ErrorAction SilentlyContinue).Source
    } else {
        Write-Warning "Python installer not found at $pythonInstaller. Skipping Python installation. Ensure Python 3.12 is available in PATH."
    }
} else {
    Write-Host "Python >=3.12 detected at $pythonCmd"
}

# 2) Install GStreamer runtime and devel if present
$gstRuntime = Join-Path $Deps 'gstreamer-1.0-msvc-x86_64-1.26.7.msi'
$gstDevel = Join-Path $Deps 'gstreamer-1.0-devel-msvc-x86_64-1.26.7.msi'
if (Test-Path $gstRuntime) {
    if (Run-Msi $gstRuntime) { Write-Host 'GStreamer runtime installed.' } else { Write-Warning 'GStreamer runtime install FAILED.' }
} else { Write-Host 'GStreamer runtime MSI not found, skipping.' }
if (Test-Path $gstDevel) {
    if (Run-Msi $gstDevel) { Write-Host 'GStreamer devel installed.' } else { Write-Warning 'GStreamer devel install FAILED.' }
} else { Write-Host 'GStreamer devel MSI not found, skipping.' }

# 3) Install Redis MSI if present (this will usually create the Windows service)
$redisMsi = Join-Path $Deps 'Redis-x64-5.0.14.1.msi'
if (Test-Path $redisMsi) {
    Write-Host 'Installing Redis MSI (may create service)...'
    if (Run-Msi $redisMsi) { Write-Host 'Redis MSI installed.' } else { Write-Warning 'Redis MSI install FAILED.' }
} else { Write-Host 'Redis MSI not found, skipping.' }

# 4) Extract gvsbuild wheels if present for later pip installation
$gvsZip = Join-Path $Deps 'GTK3_Gvsbuild_2025.10.0_x64.zip'
$gvsExtract = Join-Path $Env:TEMP 'gvsbuild_extracted'
if (Test-Path $gvsZip) {
    Write-Host "Extracting gvsbuild to $gvsExtract"
    if (Test-Path $gvsExtract) { Remove-Item -Recurse -Force $gvsExtract }
    Expand-Archive -Path $gvsZip -DestinationPath $gvsExtract -Force
} else { Write-Host 'gvsbuild zip not found, skipping extraction.' }

# 5) Create virtualenv in .venv using python
$venvPath = Join-Path $RepoRoot '.venv'
if (-not (Test-Path (Join-Path $venvPath 'Scripts' 'python.exe'))) {
    if (-not $pythonCmd) {
        Write-Error 'Python executable not found. Install Python 3.12 and re-run this script.'
        exit 2
    }
    Write-Host 'Creating virtualenv in .venv'
    & $pythonCmd -m venv $venvPath
}

$venvPython = Join-Path $venvPath 'Scripts' 'python.exe'
$venvPip = Join-Path $venvPath 'Scripts' 'pip.exe'

Write-Host 'Upgrading pip in venv'
& $venvPython -m pip install --upgrade pip setuptools wheel

# 6) Install local wheels from gvsbuild (if any)
if (Test-Path $gvsExtract) {
    $wheelDirs = Get-ChildItem -Path $gvsExtract -Recurse -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'wheels') -or Test-Path (Join-Path $_.FullName 'python') }
    foreach ($d in $wheelDirs) {
        $cands = Get-ChildItem -Path $d.FullName -Recurse -Include *.whl -ErrorAction SilentlyContinue
        if ($cands) {
            foreach ($w in $cands) {
                Write-Host "Installing wheel: $($w.FullName)"
                & $venvPip install --no-deps $w.FullName
            }
        }
    }
}

# 7) Install redis client pinned to 3.x (compatibility with OpenOB)
Write-Host 'Installing redis client pin (redis<4.0)'
& $venvPip install "redis<4.0,>=3.5.3"

# 8) Install the OpenOB package from the repository (assume openob/ subfolder or repo root)
$openobPkg = Join-Path $RepoRoot 'openob'
if (Test-Path $openobPkg) {
    Write-Host 'Installing OpenOB from ./openob'
    & $venvPip install $openobPkg
} else {
    Write-Host 'Installing OpenOB from repository root'
    & $venvPip install $RepoRoot
}

# 9) Create gstreamer.pth in venv site-packages if GStreamer was installed to default path
$gstSite = 'C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\site-packages'
if (Test-Path $gstSite) {
    $sitePackages = & $venvPython -c "import site,sys; print([p for p in site.getsitepackages() if 'site-packages' in p][0])"
    $pthFile = Join-Path $sitePackages 'gstreamer.pth'
    Write-Host "Writing gstreamer.pth -> $pthFile"
    $gstSite | Out-File -FilePath $pthFile -Encoding ASCII
} else {
    Write-Host 'GStreamer site-packages not found in default location; skipping .pth creation.'
}

# 10) Start Redis service if installed
try {
    $svc = Get-Service -Name Redis -ErrorAction SilentlyContinue
    if ($svc) {
        if ($svc.Status -ne 'Running') {
            Write-Host 'Starting Redis service'
            Start-Service -Name Redis
        } else {
            Write-Host 'Redis service already running'
        }
    } else {
        Write-Host 'Redis service not found; if you installed Redis via zip, install the service manually or run the provided install script.'n
    }
} catch {
    Write-Warning 'Could not query/start Redis service.'
}

Write-Host 'install_openob.ps1 finished. Verify steps above for errors.'
