$ErrorActionPreference = 'Stop'
$d = 'C:\Users\38495\OneDrive\文档\deepseek-harness\default-workspace\blue-whale-pet\release\windows'
$p = Join-Path $env:TEMP 'bwpet-inst6'
if (Test-Path $p) { Remove-Item -Recurse -Force $p }
$setup = Join-Path $d 'BlueWhalePet-Setup-1.0.0.exe'
$r = Start-Process -FilePath $setup -ArgumentList '/S', ('/D=' + $p) -Wait -PassThru
Start-Sleep -Seconds 2
$files = (Get-ChildItem $p -Recurse -File -ErrorAction SilentlyContinue).Count
Write-Output ("install_exit=$($r.ExitCode) files=$files")
$reg = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\BlueWhalePet' -ErrorAction SilentlyContinue
Write-Output ("display_name=" + $reg.DisplayName)
$exe = Join-Path $p 'BlueWhalePet.exe'
if (Test-Path $exe) {
    $v = (Get-Item $exe).VersionInfo
    Write-Output ("installed_product=" + $v.ProductName)
    $st = Start-Process -FilePath $exe -ArgumentList '--selftest' -Wait -PassThru
    Write-Output ("selftest_exit=" + $st.ExitCode)
}
$r2 = Start-Process -FilePath (Join-Path $p 'uninstall.exe') -ArgumentList '/uninstall', '/S' -Wait -PassThru
Write-Output ("uninstall_exit=$($r2.ExitCode)")
Start-Sleep -Seconds 3
Write-Output ("dir_exists=" + (Test-Path $p))
Write-Output ("reg_after=" + (Test-Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\BlueWhalePet'))
$lnk = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\蓝色大肥鱼.lnk'
Write-Output ("lnk_before=" + (Test-Path $lnk))
