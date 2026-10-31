# Desktop pet idle memory sampling (Lead QA)
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File qa/measure_memory.ps1 -Exe "<exe>"
param(
  [Parameter(Mandatory=$true)][string]$Exe,
  [int]$DurationSec = 12,
  [int]$SettleSec = 5,
  [string]$OutFile = ""
)
$ErrorActionPreference = "Stop"
$exePath = (Resolve-Path $Exe).Path
$exeName = [System.IO.Path]::GetFileNameWithoutExtension($exePath)
if (-not $OutFile) { $OutFile = Join-Path (Split-Path $PSScriptRoot) "qa/out/memory_report.json" }
New-Item -ItemType Directory -Force -Path (Split-Path $OutFile) | Out-Null

$existing = Get-Process -Name $exeName -ErrorAction SilentlyContinue
if ($existing) { $existing | Stop-Process -Force; Start-Sleep -Milliseconds 500 }

$proc = Start-Process -FilePath $exePath -ArgumentList @("--config", (Join-Path (Split-Path $exePath) "qa-mem-config.json")) -PassThru
Start-Sleep -Seconds $SettleSec
$samples = @()
for ($i = 0; $i -lt $DurationSec; $i++) {
  $procs = Get-Process -Name $exeName -ErrorAction SilentlyContinue
  if (-not $procs) { break }
  $ws = ($procs | Measure-Object -Property WorkingSet64 -Sum).Sum
  $priv = ($procs | Measure-Object -Property PrivateMemorySize64 -Sum).Sum
  $cpu = ($procs | Measure-Object -Property CPU -Sum).Sum
  $samples += [pscustomobject]@{
    t = $i
    processes = $procs.Count
    pids = @($procs.Id)
    working_set_mb = [math]::Round($ws / 1MB, 2)
    private_mb = [math]::Round($priv / 1MB, 2)
    cpu_seconds = [math]::Round($cpu, 2)
  }
  Start-Sleep -Seconds 1
}
$all = Get-Process -Name $exeName -ErrorAction SilentlyContinue
if ($all) { $all | Stop-Process -Force }
Start-Sleep -Milliseconds 800
$residual = Get-Process -Name $exeName -ErrorAction SilentlyContinue
$ok = $samples.Count -gt 3
$maxWs = if ($samples) { ($samples | Measure-Object -Property working_set_mb -Maximum).Maximum } else { 0 }
$avgWs = if ($samples) { [math]::Round((($samples | Measure-Object -Property working_set_mb -Average).Average), 2) } else { 0 }
$result = [pscustomobject]@{
  exe = $exePath
  exe_name = $exeName
  ok = $ok
  samples = $samples
  max_working_set_mb = $maxWs
  avg_working_set_mb = $avgWs
  target_mb = 60
  target_met = ($maxWs -le 60)
  residual_processes = @($residual).Count
  timestamp = (Get-Date).ToString("o")
}
$result | ConvertTo-Json -Depth 6 | Set-Content -Path $OutFile -Encoding UTF8
Write-Output ("MEMORY " + ($(if ($result.target_met) { "OK" } else { "WARN" })) + " max=" + $maxWs + "MB avg=" + $avgWs + "MB processes=" + ($samples[0].processes) + " report=" + $OutFile)
if ($result.residual_processes -gt 0) { Write-Output "WARN: process still running" }
if (-not $ok) { exit 1 }
if (-not $result.target_met) { exit 2 }
exit 0
