$url = 'https://gstreamer.freedesktop.org/data/pkg/windows/1.27.50/msvc_x86_64/gstreamer-1.0-msvc-x86_64-1.27.50.zip'
$out = Join-Path $PSScriptRoot '.downloads\gstreamer-1.27.50-msvc_x86_64.zip'
Write-Host "Downloading $url to $out"
Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing
$dest = Join-Path $PSScriptRoot 'openob-embedded-installer\packaging\gstreamer-1.27.50\msvc_x86_64'
Write-Host "Extracting to $dest"
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
Expand-Archive -Path $out -DestinationPath $dest -Force
Write-Host "Done; listing top-level dirs in $dest"
Get-ChildItem -Path $dest | Select-Object Name,PSIsContainer | Format-Table -AutoSize
