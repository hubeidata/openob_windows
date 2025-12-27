Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}

function Get-InstallerRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

function Read-VersionsJson {
    $installerRoot = Get-InstallerRoot
    $versionsPath = Join-Path $installerRoot 'installer\config\versions.json'
    if (-not (Test-Path $versionsPath)) {
        throw "versions.json not found: $versionsPath"
    }
    return (Get-Content -Raw -Path $versionsPath | ConvertFrom-Json)
}

function Get-RuntimeRoot {
    $installerRoot = Get-InstallerRoot
    return (Resolve-Path (Join-Path $installerRoot 'packaging\openob_runtime')).Path
}

function Get-EmbeddedPythonDir {
    return (Join-Path (Get-RuntimeRoot) 'python')
}

function Get-EmbeddedPythonExe {
    return (Join-Path (Get-EmbeddedPythonDir) 'python.exe')
}

function Assert-Command {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "Required command not found on PATH: $Name"
    }
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Invoke-Download {
    param(
        [string]$Url,
        [string]$OutFile
    )

    Ensure-Directory (Split-Path -Parent $OutFile)
    Write-Host "Downloading: $Url"
    Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
}

function Expand-ZipTo {
    param(
        [string]$ZipPath,
        [string]$Destination
    )

    if (Test-Path $Destination) {
        Remove-Item -Recurse -Force $Destination
    }
    Ensure-Directory $Destination

    # PowerShell 5.1 (.NET Framework) does not support the ZipFile.ExtractToDirectory
    # overload with an overwrite boolean. Expand-Archive works reliably here.
    Expand-Archive -Path $ZipPath -DestinationPath $Destination -Force
}
