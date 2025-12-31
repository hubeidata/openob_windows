$dist = 'C:\Users\vamanuel\Documents\openob_windows\openob-embedded-installer\dist'
Set-Location -Path $dist
$installer = Join-Path $dist 'OpenOB-Setup-4.0.3.exe'
$target = 'C:\Temp\openob_test_install_5'
if(Test-Path $target){ Remove-Item -Path $target -Recurse -Force -ErrorAction SilentlyContinue }
$p = Start-Process -FilePath $installer -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',"/DIR=$target" -Wait -PassThru
Write-Output "ExitCode:$($p.ExitCode)"
if(Test-Path $target){
    Get-ChildItem -Path $target -Recurse | Select-Object -ExpandProperty FullName | Out-File -FilePath 'C:\Temp\openob_installed_files_5.txt' -Encoding utf8
    Write-Output 'Listing saved to C:\Temp\openob_installed_files_5.txt'
}else{
    Write-Output 'Target dir not found'
}