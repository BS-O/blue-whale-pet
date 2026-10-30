# Windows 安装版安装/卸载往返验证（Lead QA）
# 用法: powershell -NoProfile -ExecutionPolicy Bypass -File qa/verify_installer.ps1 -Setup "release/windows/BlueWhalePet-Setup-1.0.0.exe"
param(
  [Parameter(Mandatory=$true)][string]$Setup,
  [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "Programs\BlueWhalePet"),
  [string]$OutFile = ""
)
$ErrorActionPreference = "Continue"
$setupPath = (Resolve-Path $Setup).Path
if (-not $OutFile) { $OutFile = Join-Path (Split-Path $PSScriptRoot) "qa/out/installer_report.json" }
New-Item -ItemType Directory -Force -Path (Split-Path $OutFile) | Out-Null

$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\蓝鲸桌宠.lnk"
$startMenuAlt = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\BlueWhalePet.lnk"
$desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "蓝鲸桌宠.lnk"
$desktopAlt = Join-Path ([Environment]::GetFolderPath("Desktop")) "BlueWhalePet.lnk"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$uninstKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\BlueWhalePet"
$appDataCfg = Join-Path $env:APPDATA "BlueWhalePet"
$report = [ordered]@{ setup = $setupPath; install_dir = $InstallDir; steps = @(); ok = $false }

function Step($name, $ok, $detail = "") {
  $script:report.steps += [ordered]@{ step = $name; ok = [bool]$ok; detail = "$detail" }
  Write-Output ("[" + $(if ($ok) { "OK" } else { "FAIL" }) + "] " + $name + " " + $detail)
}

# 清理历史状态
Get-Process -Name "BlueWhalePet" -ErrorAction SilentlyContinue | Stop-Process -Force
if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir -ErrorAction SilentlyContinue }
foreach ($p in @($startMenu, $startMenuAlt, $desktop, $desktopAlt)) { if (Test-Path $p) { Remove-Item -Force $p } }
Remove-Item -Path $uninstKey -Recurse -ErrorAction SilentlyContinue

# 1. 静默安装
$p = Start-Process -FilePath $setupPath -ArgumentList @("/S", "/D=$InstallDir") -PassThru -Wait
Step "silent-install-exit" ($p.ExitCode -eq 0) ("exit=" + $p.ExitCode)
Start-Sleep -Seconds 2

# 2. 文件检查
$appExe = Join-Path $InstallDir "BlueWhalePet.exe"
Step "install-dir" (Test-Path $InstallDir) $InstallDir
Step "app-exe" (Test-Path $appExe) $appExe
$unins = Join-Path $InstallDir "uninstall.exe"
Step "uninstaller-copied" (Test-Path $unins) $unins
$assetsDir = Join-Path $InstallDir "_internal\assets"
$assetsDir2 = Join-Path $InstallDir "assets"
Step "assets-present" ((Test-Path $assetsDir) -or (Test-Path $assetsDir2)) "need assets bundled"

# 3. 快捷方式/注册表
Step "start-menu-shortcut" ((Test-Path $startMenu) -or (Test-Path $startMenuAlt)) "start menu lnk"
$lnk = if (Test-Path $startMenu) { $startMenu } else { $startMenuAlt }
if (Test-Path $lnk) {
  $sh = New-Object -ComObject WScript.Shell
  $target = $sh.CreateShortcut($lnk).TargetPath
  Step "shortcut-target" ($target -like "*$InstallDir*") $target
}
Step "uninstall-registry" (Test-Path $uninstKey) $uninstKey
if (Test-Path $uninstKey) {
  $kv = Get-ItemProperty $uninstKey
  Step "registry-displayname" ($kv.DisplayName -ne $null) ("DisplayName=" + $kv.DisplayName)
  Step "registry-version" ($kv.DisplayVersion -eq "1.0.0") ("DisplayVersion=" + $kv.DisplayVersion)
  Step "registry-uninstallstring" ($kv.UninstallString -ne $null) ("UninstallString=" + $kv.UninstallString)
}

# 4. 运行自检（窗口版 exe：读 selftest 报告文件）
$reportFile = Join-Path $appDataCfg "selftest_report.json"
Remove-Item $reportFile -Force -ErrorAction SilentlyContinue
$run = Start-Process -FilePath $appExe -ArgumentList @("--selftest") -PassThru -Wait
Start-Sleep -Seconds 1
if (Test-Path $reportFile) {
  Step "installed-selftest" $true ("report=" + $reportFile)
} else {
  Step "installed-selftest" ($run.ExitCode -eq 0) ("exit=" + $run.ExitCode + " (无报告文件)")
}

# 5. 启动→进程存在→托盘（间接：进程持续存在 4s）
$app = Start-Process -FilePath $appExe -PassThru
Start-Sleep -Seconds 4
$alive = Get-Process -Id $app.Id -ErrorAction SilentlyContinue
Step "launch-alive" ($alive -ne $null) ("pid=" + $app.Id)
if ($alive) {
  $ws = [math]::Round($alive.WorkingSet64 / 1MB, 1)
  $report["running_working_set_mb"] = $ws
  Step "running-memory" ($ws -le 70) ("WorkingSet=" + $ws + "MB")
  Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 1

# 6. 静默卸载
if (Test-Path $unins) {
  $u = Start-Process -FilePath $unins -ArgumentList @("/uninstall", "/S") -PassThru -Wait
  Step "silent-uninstall-exit" ($u.ExitCode -eq 0) ("exit=" + $u.ExitCode)
  Start-Sleep -Seconds 2
} else {
  Step "silent-uninstall" $false "uninstall.exe 缺失"
}

# 7. 残留检查
Step "residual-install-dir" (-not (Test-Path $InstallDir)) "should be gone"
Step "residual-start-menu" ((-not (Test-Path $startMenu)) -and (-not (Test-Path $startMenuAlt))) "should be gone"
Step "residual-desktop" ((-not (Test-Path $desktop)) -and (-not (Test-Path $desktopAlt))) "should be gone"
Step "residual-registry" (-not (Test-Path $uninstKey)) "should be gone"
$runVal = (Get-ItemProperty -Path $runKey -ErrorAction SilentlyContinue).BlueWhalePet
Step "residual-autostart" (-not $runVal) ("Run=" + $runVal)
Get-Process -Name "BlueWhalePet" -ErrorAction SilentlyContinue | Stop-Process -Force

$failed = @($report.steps | Where-Object { -not $_.ok })
$report["failed_count"] = $failed.Count
$report["ok"] = ($failed.Count -eq 0)
$report["timestamp"] = (Get-Date).ToString("o")
$report | ConvertTo-Json -Depth 6 | Set-Content -Path $OutFile -Encoding UTF8
Write-Output ("INSTALLER " + $(if ($report.ok) { "OK" } else { "FAIL" }) + " failed=" + $failed.Count + " report=" + $OutFile)
if ($failed.Count -gt 0) { $failed | ForEach-Object { Write-Output ("  - " + $_.step + " " + $_.detail) }; exit 1 }
exit 0
