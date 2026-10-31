# -*- mode: python ; coding: utf-8 -*-
"""蓝鲸桌宠自研安装器（PyInstaller onefile，windowed，纯 Python/tkinter）。

构建（由 build_all.ps1 调用，必须设置环境变量）：
  PET_PAYLOAD_ZIP  = onedir 应用目录压缩成的 payload.zip（安装载荷，解压到安装目录）
  PET_BUILD_ROOT   = 构建临时根目录（可选，仅用于日志）
产物：dist/BlueWhalePet-Setup.exe（由 build_all.ps1 复制为
      release/windows/BlueWhalePet-Setup-1.0.0.exe）

安装器自身不依赖 Pillow：Tk 8.6 原生支持 PNG；快捷方式通过系统 PowerShell
WScript.Shell COM 创建（无需 Inno Setup/NSIS 等外部打包工具）。
"""
import os

APP_NAME = "BlueWhalePet-Setup"

SPEC_DIR = os.path.abspath(globals().get("SPECPATH") or os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.abspath(os.path.join(SPEC_DIR, "..", "..", ".."))
ASSETS = os.path.join(ROOT, "assets")
INSTALLER_ASSETS = os.path.join(ASSETS, "installer")

PAYLOAD_ZIP = os.environ.get("PET_PAYLOAD_ZIP", "")
if not PAYLOAD_ZIP or not os.path.isfile(PAYLOAD_ZIP):
    raise SystemExit(
        "installer.spec: 需要环境变量 PET_PAYLOAD_ZIP 指向已存在的 payload.zip（先跑 build_all.ps1）"
    )

a = Analysis(
    [os.path.join(SPEC_DIR, "installer_main.py")],
    pathex=[SPEC_DIR],
    binaries=[],
    datas=[
        (PAYLOAD_ZIP, "."),
        (os.path.join(INSTALLER_ASSETS, "banner.png"), "."),
        (os.path.join(INSTALLER_ASSETS, "side.png"), "."),
        (os.path.join(INSTALLER_ASSETS, "setup.ico"), "."),
    ],
    hiddenimports=[
        "tkinter",
        "tkinter.ttk",
        "tkinter.messagebox",
        "tkinter.filedialog",
        "tkinter.font",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PIL",
        "numpy",
        "pandas",
        "scipy",
        "matplotlib",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "IPython",
        "pytest",
        "setuptools",
        "pip",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(INSTALLER_ASSETS, "setup.ico"),
    version=os.path.join(SPEC_DIR, "..", "version_info_installer.txt"),
)
