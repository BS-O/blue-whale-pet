$ErrorActionPreference = 'Stop'
$d = 'C:\Users\38495\OneDrive\文档\deepseek-harness\default-workspace\blue-whale-pet\release\windows'
icacls $d /setintegritylevel Medium | Out-Null
foreach ($f in @('BlueWhalePet-Portable-1.0.0.exe', 'BlueWhalePet-Setup-1.0.0.exe')) {
    icacls (Join-Path $d $f) /setintegritylevel Medium | Out-Null
}
$p = Join-Path $env:TEMP 'bwpet-inst5'
if (Test-Path $p) { Remove-Item -Recurse -Force $p }
$setup = Join-Path $d 'BlueWhalePet-Setup-1.0.0.exe'
$r = Start-Process -FilePath $setup -ArgumentList '/S', ('/D=' + $p) -Wait -PassThru
Start-Sleep -Seconds 2
$files = (Get-ChildItem $p -Recurse -File -ErrorAction SilentlyContinue).Count
Write-Output ("install_exit=$($r.ExitCode) files=$files")
$r2 = Start-Process -FilePath (Join-Path $p 'uninstall.exe') -ArgumentList '/uninstall', '/S' -Wait -PassThru
Write-Output ("uninstall_exit=$($r2.ExitCode)")
Start-Sleep -Seconds 3
Write-Output ("dir_exists=$(Test-Path $p)")
Write-Output ("reg=$(Test-Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\BlueWhalePet')")
$lnk = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\蓝鲸桌宠.lnk'
Write-Output ("lnk=$(Test-Path $lnk)")
