# ============================================================================
#  BlueWhalePet - Windows one-click build script (pure ASCII on purpose:
#  Windows PowerShell 5.1 decodes BOM-less .ps1 as ANSI, so avoid non-ASCII
#  literals here; all Chinese paths are derived at runtime via $PSScriptRoot).
#
#  Usage (from anywhere):
#    powershell -NoProfile -ExecutionPolicy Bypass -File packaging\windows\build_all.ps1
#    powershell ... -File packaging\windows\build_all.ps1 -SkipPortable
#    powershell ... -File packaging\windows\build_all.ps1 -KeepWork   # keep E:\pet-build-tmp
#
#  Pipeline:
#    clean -> PyInstaller onedir app -> zip payload -> PyInstaller onefile portable
#          -> PyInstaller self-made installer -> copy to release/windows
#          -> SHA256SUMS.txt -> cleanup build temp dir
#
#  Outputs (SPEC 7.3):
#    release/windows/BlueWhalePet-Portable-1.0.0.exe
#    release/windows/BlueWhalePet-Setup-1.0.0.exe
#    release/windows/SHA256SUMS.txt
#  Build intermediates: E:\pet-build-tmp (removed at the end unless -KeepWork)
# ============================================================================
[CmdletBinding()]
param(
    [string]$BuildRoot = 'E:\pet-build-tmp\pack-win',
    [string]$Version = '1.0.0',
    [switch]$SkipOnedir,
    [switch]$SkipPortable,
    [switch]$SkipInstaller,
    [switch]$SkipCleanup,
    [switch]$KeepWork,
    [switch]$QaConsoleBuild
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:Failed = $false
$script:StartTime = Get-Date

function Write-Step([string]$Message) {
    Write-Host ''
    Write-Host ('==> ' + $Message) -ForegroundColor Cyan
}

function Assert-LastExit([string]$What) {
    if ($LASTEXITCODE -ne 0) {
        throw ("{0} failed with exit code {1}" -f $What, $LASTEXITCODE)
    }
}

function Invoke-PyInstaller([string]$SpecPath, [string]$DistPath, [string]$WorkPath) {
    $cliArgs = @(
        '--noconfirm',
        '--clean',
        '--log-level', 'WARN',
        '--distpath', $DistPath,
        '--workpath', $WorkPath,
        $SpecPath
    )
    # Native stderr output (PyInstaller logs) must not become a terminating error
    # under $ErrorActionPreference = 'Stop' - switch to Continue while invoking.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $script:Py -m PyInstaller @cliArgs 2>&1
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    foreach ($line in $output) { Write-Host ('    ' + [string]$line) }
    if ($code -ne 0) {
        throw ('PyInstaller {0} failed with exit code {1}' -f (Split-Path -Leaf $SpecPath), $code)
    }
}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$PkgDir = $PSScriptRoot
$Root = Split-Path -Parent (Split-Path -Parent $PkgDir)
$SrcEntry = Join-Path $Root 'src\main.py'
$AssetsDir = Join-Path $Root 'assets'
$AppIco = Join-Path $AssetsDir 'icons\app.ico'
$SetupIco = Join-Path $AssetsDir 'installer\setup.ico'
$InstallerAssets = Join-Path $AssetsDir 'installer'
$ReleaseDir = Join-Path $Root 'release\windows'

$Work = Join-Path $BuildRoot 'work'
$Dist = Join-Path $BuildRoot 'dist'
$PayloadZip = Join-Path $BuildRoot 'payload\payload.zip'
$PayloadDir = Split-Path -Parent $PayloadZip

$PortableSpec = Join-Path $PkgDir 'pet-portable.spec'
$OnedirSpec = Join-Path $PkgDir 'pet-onedir.spec'
$InstallerSpec = Join-Path $PkgDir 'installer\installer.spec'

$PortableOut = Join-Path $ReleaseDir ("BlueWhalePet-Portable-{0}.exe" -f $Version)
$SetupOut = Join-Path $ReleaseDir ("BlueWhalePet-Setup-{0}.exe" -f $Version)
$HashFile = Join-Path $ReleaseDir 'SHA256SUMS.txt'

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
Write-Step 'Preflight checks'
$script:Py = (Get-Command py -ErrorAction SilentlyContinue)
if (-not $script:Py) { throw 'Python launcher "py" not found in PATH.' }
& py -c "import sys; print('Python', sys.version); import PyInstaller, PIL; print('PyInstaller', PyInstaller.__version__, 'Pillow', PIL.__version__)"
Assert-LastExit 'python dependency check'

foreach ($required in @($SrcEntry, $AppIco, $SetupIco, $PortableSpec, $OnedirSpec, $InstallerSpec,
        (Join-Path $PkgDir 'portable.flag'),
        (Join-Path $InstallerAssets 'banner.png'),
        (Join-Path $InstallerAssets 'side.png'),
        (Join-Path $Root 'src\main.py'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw ("missing required file: {0}" -f $required)
    }
}
if (-not (Test-Path -LiteralPath $AssetsDir -PathType Container)) { throw 'assets/ directory missing.' }

$free = (Get-PSDrive -Name ([System.IO.Path]::GetPathRoot($BuildRoot).TrimEnd(':\')) -ErrorAction SilentlyContinue)
if ($free) {
    Write-Host ("    build drive free space: {0:N2} GB" -f ($free.Free / 1GB))
}
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
# 清理历史手工测试产物（不属于交付物）
foreach ($stale in @('hello-test.exe', 'hello-x.exe')) {
    $stalePath = Join-Path $ReleaseDir $stale
    if (Test-Path -LiteralPath $stalePath) { Remove-Item -LiteralPath $stalePath -Force }
}

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------
Write-Step 'Clean build directories'
if (-not $SkipCleanup -and (Test-Path -LiteralPath $BuildRoot)) {
    Write-Host ("    removing " + $BuildRoot)
    Remove-Item -LiteralPath $BuildRoot -Recurse -Force -ErrorAction SilentlyContinue
}
foreach ($dir in @($BuildRoot, $Work, $Dist, $PayloadDir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
foreach ($old in @($PortableOut, $SetupOut)) {
    if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old -Force }
}

# DSH 工作区目录带有 Low integrity 标签，从该目录启动的 exe 会以 Low IL 运行，
# 导致 PyInstaller onefile 无法在 %TEMP% 创建解压目录（启动即失败）。
# 交付的 exe 必须重新标记为 Medium 完整性级别，QA 才能直接运行。
function Set-MediumIntegrity([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        & icacls $Path /setintegritylevel Medium | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Warning ('icacls relabel failed: ' + $Path) }
    }
}

# ---------------------------------------------------------------------------
# 1) onedir app
# ---------------------------------------------------------------------------
$OnedirDist = Join-Path $Dist 'BlueWhalePet'
if (-not $SkipOnedir -and -not $SkipInstaller) {
    Write-Step 'Build onedir application (installed edition payload)'
    Invoke-PyInstaller $OnedirSpec $Dist (Join-Path $Work 'onedir')
    if (-not (Test-Path -LiteralPath (Join-Path $OnedirDist 'BlueWhalePet.exe'))) {
        throw 'onedir build did not produce BlueWhalePet\BlueWhalePet.exe'
    }
    $size = (Get-ChildItem -LiteralPath $OnedirDist -Recurse -File | Measure-Object -Property Length -Sum).Sum
    Write-Host ("    onedir size: {0:N1} MB" -f ($size / 1MB))

    Write-Step 'Create payload.zip for installer'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    if (Test-Path -LiteralPath $PayloadZip) { Remove-Item -LiteralPath $PayloadZip -Force }
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $OnedirDist,
        $PayloadZip,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $false
    )
    $zipSize = (Get-Item -LiteralPath $PayloadZip).Length
    Write-Host ("    payload.zip: {0:N1} MB" -f ($zipSize / 1MB))
} elseif (-not $SkipInstaller) {
    if (-not (Test-Path -LiteralPath $PayloadZip)) { throw 'SkipOnedir set but payload.zip does not exist.' }
}

# ---------------------------------------------------------------------------
# 2) portable onefile exe
# ---------------------------------------------------------------------------
if (-not $SkipPortable) {
    Write-Step 'Build portable onefile exe (windowed, with portable.flag)'
    Invoke-PyInstaller $PortableSpec $Dist (Join-Path $Work 'portable')
    $portableBuilt = Join-Path $Dist 'BlueWhalePet.exe'
    if (-not (Test-Path -LiteralPath $portableBuilt)) {
        throw 'portable build did not produce BlueWhalePet.exe'
    }
    Copy-Item -LiteralPath $portableBuilt -Destination $PortableOut -Force
    $size = (Get-Item -LiteralPath $PortableOut).Length
    Write-Host ("    {0} : {1:N1} MB" -f (Split-Path -Leaf $PortableOut), ($size / 1MB))
}

# ---------------------------------------------------------------------------
# 3) installer onefile exe (embeds payload.zip)
# ---------------------------------------------------------------------------
if (-not $SkipInstaller) {
    Write-Step 'Build self-made installer exe (tkinter wizard, embeds payload.zip)'
    $env:PET_PAYLOAD_ZIP = $PayloadZip
    $env:PET_BUILD_ROOT = $BuildRoot
    try {
        Invoke-PyInstaller $InstallerSpec $Dist (Join-Path $Work 'installer')
    } finally {
        Remove-Item Env:\PET_PAYLOAD_ZIP -ErrorAction SilentlyContinue
        Remove-Item Env:\PET_BUILD_ROOT -ErrorAction SilentlyContinue
    }
    $setupBuilt = Join-Path $Dist 'BlueWhalePet-Setup.exe'
    if (-not (Test-Path -LiteralPath $setupBuilt)) {
        throw 'installer build did not produce BlueWhalePet-Setup.exe'
    }
    Copy-Item -LiteralPath $setupBuilt -Destination $SetupOut -Force
    $size = (Get-Item -LiteralPath $SetupOut).Length
    Write-Host ("    {0} : {1:N1} MB" -f (Split-Path -Leaf $SetupOut), ($size / 1MB))
}

# ---------------------------------------------------------------------------
# 4) optional QA console build (NOT delivered): lets us capture stdout of
#    --version/--selftest, which a windowed exe cannot print (per lead).
# ---------------------------------------------------------------------------
if ($QaConsoleBuild) {
    Write-Step 'Build QA console variant (internal only, not shipped)'
    $QaDist = Join-Path $BuildRoot 'qa-dist'
    $env:PET_BUILD_CONSOLE = '1'
    try {
        Invoke-PyInstaller $PortableSpec $QaDist (Join-Path $Work 'qa-console')
    } finally {
        Remove-Item Env:\PET_BUILD_CONSOLE -ErrorAction SilentlyContinue
    }
    $qaExe = Join-Path $QaDist 'BlueWhalePet.exe'
    if (Test-Path -LiteralPath $qaExe) {
        $qaLog = Join-Path $BuildRoot 'qa-console-output.txt'
        $lines = @()
        $previous = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $lines += '### ' + $qaExe + ' --version'
            $lines += (& $qaExe --version 2>&1 | Out-String).Trim()
            $lines += '### ' + $qaExe + ' --selftest'
            $lines += (& $qaExe --selftest 2>&1 | Out-String).Trim()
        } finally {
            $ErrorActionPreference = $previous
        }
        [System.IO.File]::WriteAllLines($qaLog, $lines, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host ("    QA console output saved: " + $qaLog)
        Write-Host '    ---- QA console output begin ----'
        foreach ($line in (Get-Content -LiteralPath $qaLog -Encoding UTF8)) { Write-Host ('    ' + $line) }
        Write-Host '    ---- QA console output end ----'
    }
}

Write-Step 'Restore Medium integrity for artifacts (DSH workspace inherits Low IL)'
& icacls $ReleaseDir /setintegritylevel '(OI)(CI)Medium' | Out-Null
foreach ($artifact in @($PortableOut, $SetupOut)) { Set-MediumIntegrity $artifact }
Write-Host '    done'

# ---------------------------------------------------------------------------
# 5) hashes + summary
# ---------------------------------------------------------------------------
Write-Step 'SHA256SUMS'
$hashLines = @()
foreach ($artifact in @($PortableOut, $SetupOut)) {
    if (Test-Path -LiteralPath $artifact) {
        $hash = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant()
        $hashLines += ('{0}  {1}' -f $hash, (Split-Path -Leaf $artifact))
        Write-Host ('    ' + (Split-Path -Leaf $artifact) + '  ' + $hash)
    }
}
if ($hashLines.Count -gt 0) {
    [System.IO.File]::WriteAllLines($HashFile, $hashLines, (New-Object System.Text.UTF8Encoding($false)))
    Set-MediumIntegrity $HashFile
}

Write-Step 'Artifacts'
foreach ($artifact in @($PortableOut, $SetupOut)) {
    if (Test-Path -LiteralPath $artifact) {
        $item = Get-Item -LiteralPath $artifact
        Write-Host ('    {0}  ({1:N1} MB)' -f $item.FullName, ($item.Length / 1MB)) -ForegroundColor Green
    }
}

# ---------------------------------------------------------------------------
# 6) cleanup build temp dir
# ---------------------------------------------------------------------------
if (-not $KeepWork) {
    Write-Step 'Cleanup build intermediates'
    if (Test-Path -LiteralPath $BuildRoot) {
        Remove-Item -LiteralPath $BuildRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Host ('    removed ' + $BuildRoot)
} else {
    Write-Host ('    kept build intermediates: ' + $BuildRoot)
}

$elapsed = (Get-Date) - $script:StartTime
Write-Host ''
Write-Host ('BUILD OK in {0:N1}s' -f $elapsed.TotalSeconds) -ForegroundColor Green
