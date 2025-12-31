$src = 'C:\Program Files\GStreamer\1.0\msvc_x86_64'
$dst = Join-Path $PSScriptRoot 'openob-embedded-installer\packaging\gstreamer-1.27.50\msvc_x86_64'
Write-Host "Copying $src -> $dst"
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
Copy-Item -Path $src -Destination $dst -Recurse -Force
Write-Host 'Copy complete. Top-level of destination:'
Get-ChildItem -Path $dst | Select-Object Name,PSIsContainer | Format-Table -AutoSize
