[CmdletBinding()]
param(
    [string]$IsccPath,
    [string]$IssPath
)

. "$PSScriptRoot\_lib.ps1"

function Find-Iscc {
    param([string]$Preferred)

    if ($Preferred -and (Test-Path $Preferred)) { return $Preferred }

    $cmd = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) { return $cmd.Source }

    $candidates = @(
        'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        'C:\Program Files\Inno Setup 6\ISCC.exe'
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }

    # Registry-based discovery (common Inno Setup installers)
    $regKeys = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
    )
    foreach ($root in $regKeys) {
        $sub = Get-ChildItem $root -ErrorAction SilentlyContinue | ForEach-Object {
            Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
        } | Where-Object {
            $_.DisplayName -like 'Inno Setup*' -and $_.InstallLocation
        } | Select-Object -First 1

        if ($sub -and $sub.InstallLocation) {
            $p = Join-Path $sub.InstallLocation 'ISCC.exe'
            if (Test-Path $p) { return $p }
        }
    }

    return $null
}

$versions = Read-VersionsJson
$IsccPath = Find-Iscc -Preferred $IsccPath
if (-not $IssPath) {
    $IssPath = Join-Path (Get-InstallerRoot) 'installer\inno\openob-installer.iss'
}

if (-not (Test-Path $IsccPath)) {
    $fallback = $versions.innoSetup.defaultIsccPath
    throw "ISCC.exe not found. Install Inno Setup 6 or pass -IsccPath. Default expected: $fallback"
}
if (-not (Test-Path $IssPath)) {
    throw "ISS script not found: $IssPath"
}

$runtimeRoot = Get-RuntimeRoot
$pyExe = Get-EmbeddedPythonExe
if (-not (Test-Path $pyExe)) {
    throw "Embedded runtime missing (python.exe not found). Build the runtime first. Expected: $pyExe"
}

Write-Host "Building installer with: $IsccPath"
Write-Host "ISS: $IssPath"

$appName = $versions.app.name
$appVersion = $versions.app.version

function Get-OpenOBVersionFromRuntime {
    param([string]$PythonExe)
    try {
        $v = & $PythonExe -c "import importlib.metadata as m; print(m.version('OpenOB'))" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v) { return ($v | Out-String).Trim() }
    } catch {
        return $null
    }
    return $null
}

if (-not $appVersion -or $appVersion -eq '0.0.0') {
    $detected = Get-OpenOBVersionFromRuntime -PythonExe $pyExe
    if ($detected) {
        $appVersion = $detected
        Write-Host "Using detected OpenOB version from runtime: $appVersion"
    } else {
        Write-Host "Could not detect OpenOB version from runtime; using versions.json: $appVersion"
    }
}
Write-Host "AppName: $appName"
Write-Host "AppVersion: $appVersion"

& $IsccPath "/DAppNameOverride=$appName" "/DAppVersionOverride=$appVersion" $IssPath

$distDir = Join-Path (Get-InstallerRoot) 'dist'
Write-Host "Done. Dist folder: $distDir"
