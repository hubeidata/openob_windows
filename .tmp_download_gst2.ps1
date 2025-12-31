$url = 'https://gstreamer.freedesktop.org/data/pkg/windows/1.27.50/msvc_x86_64/gstreamer-1.0-msvc-x86_64-1.27.50.zip'
$out = Join-Path $PSScriptRoot '.downloads\gstreamer-1.27.50-msvc_x86_64.zip'
Write-Host "Attempting download with custom User-Agent: $url -> $out"
$headers = @{ 'User-Agent' = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' }
Invoke-WebRequest -Uri $url -OutFile $out -Headers $headers -UseBasicParsing
if (-not (Test-Path $out)) { throw "Download failed; no file at $out" }
$dest = Join-Path $PSScriptRoot 'openob-embedded-installer\packaging\gstreamer-1.27.50\msvc_x86_64'
Write-Host "Extracting to $dest"
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
Expand-Archive -Path $out -DestinationPath $dest -Force
Write-Host "Done; listing top-level dirs in $dest"
Get-ChildItem -Path $dest | Select-Object Name,PSIsContainer | Format-Table -AutoSize
