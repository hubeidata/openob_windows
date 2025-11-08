# create_ui_shortcut.ps1 — create a Desktop shortcut that launches run_ui.bat
$desktop = [Environment]::GetFolderPath('Desktop')
$repoRoot = (Resolve-Path "$(Split-Path -Parent $MyInvocation.MyCommand.Path)\..").Path
$target = Join-Path $repoRoot 'scripts\run_ui.vbs'
$lnkPath = Join-Path $desktop 'OpenOB UI.lnk'

# Prefer the bundled .ico in ui\images if present
$iconPath = Join-Path $repoRoot 'ui\images\ob-logo.ico'
if (-not (Test-Path $iconPath)) { $iconPath = $null }

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($lnkPath)
$Shortcut.TargetPath = $target
$Shortcut.WorkingDirectory = $repoRoot
$Shortcut.WindowStyle = 1
if ($iconPath) { $Shortcut.IconLocation = $iconPath }
$Shortcut.Save()
Write-Host "Shortcut created: $lnkPath"
