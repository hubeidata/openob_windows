[CmdletBinding()]
param(
    [string]$PythonVersion,
    [string]$Arch = 'amd64'
)

. "$PSScriptRoot\_lib.ps1"

$versions = Read-VersionsJson
if (-not $PythonVersion) {
    $PythonVersion = $versions.python.version
}

$runtimeRoot = Get-RuntimeRoot
$pyDir = Get-EmbeddedPythonDir
Ensure-Directory $pyDir

# Download embeddable zip
$urlTemplate = $versions.python.embedZipUrl
$zipUrl = $urlTemplate.Replace('{version}', $PythonVersion)
$downloadsDir = Join-Path (Get-InstallerRoot) '.downloads'
$zipPath = Join-Path $downloadsDir "python-$PythonVersion-embed-$Arch.zip"
Invoke-Download -Url $zipUrl -OutFile $zipPath

Write-Host "Extracting $zipPath -> $pyDir"
Expand-ZipTo -ZipPath $zipPath -Destination $pyDir

$pyExe = Get-EmbeddedPythonExe
if (-not (Test-Path $pyExe)) {
    throw "python.exe not found after extraction: $pyExe"
}

# Enable site-packages for embeddable python
$pthFile = Get-ChildItem -Path $pyDir -Filter 'python*._pth' | Select-Object -First 1
if (-not $pthFile) {
    throw "Could not find python*._pth in $pyDir"
}

Write-Host "Configuring embeddable path file: $($pthFile.FullName)"
$content = Get-Content -Path $pthFile.FullName

# Ensure Lib\site-packages is present
$hasSitePackages = $content | Where-Object { $_.Trim() -ieq 'Lib\site-packages' }
if (-not $hasSitePackages) {
    $content += 'Lib\site-packages'
}

# Ensure import site is enabled (uncomment or add)
$hasImportSite = $content | Where-Object { $_.Trim() -ieq 'import site' -or $_.Trim() -ieq '#import site' }
if (-not $hasImportSite) {
    $content += 'import site'
} else {
    $content = $content | ForEach-Object {
        if ($_.Trim() -ieq '#import site') { 'import site' } else { $_ }
    }
}

Set-Content -Encoding ASCII -Path $pthFile.FullName -Value $content

# Ensure site-packages directory exists
Ensure-Directory (Join-Path $pyDir 'Lib\site-packages')

Write-Host "Embedded Python ready: $pyExe"
