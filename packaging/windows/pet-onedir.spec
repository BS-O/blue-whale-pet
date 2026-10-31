# -*- mode: python ; coding: utf-8 -*-
"""蓝色大肥鱼 Windows 安装版应用（PyInstaller onedir，windowed）。

构建：
    py -m PyInstaller --noconfirm --clean \
        --distpath E:\\pet-build-tmp\\dist --workpath E:\\pet-build-tmp\\work\\onedir \
        packaging\\windows\\pet-onedir.spec
产物：dist/BlueWhalePet/BlueWhalePet.exe（连同 _internal/ 与 assets/ 由 build_all.ps1
      打包成 payload.zip，供自研安装器安装到 %LOCALAPPDATA%\\Programs\\BlueWhalePet）。

与便携版差异：不含 portable.flag（安装版数据目录 = %APPDATA%\\BlueWhalePet）。
"""
import os

APP_NAME = "BlueWhalePet"
APP_VERSION = "1.0.0"

SPEC_DIR = os.path.abspath(globals().get("SPECPATH") or os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.abspath(os.path.join(SPEC_DIR, "..", ".."))

hiddenimports = [
    # src/ 顶层模块（入口通过 sys.path 绝对导入，含 __import__ 动态导入）
    "app",
    "anim",
    "anim.frames",
    "anim.manifest",
    "anim.state",
    "api",
    "autostart",
    "bubble",
    "chat",
    "cli",
    "config",
    "constants",
    "logging_setup",
    "pet_window",
    "platform_linux",
    "platform_win",
    "prompts",
    "resources",
    "selftest",
    "settings_window",
    "showcase",
    "single_instance",
    "tray",
    "tray_win",
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
    "tkinter.filedialog",
    "tkinter.simpledialog",
    "tkinter.colorchooser",
    "tkinter.font",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL.ImageFilter",
    "PIL.ImageOps",
    "PIL.ImageEnhance",
    "PIL.ImageChops",
    "PIL.ImageGrab",
    "PIL.PngImagePlugin",
    "PIL._tkinter_finder",
]

a = Analysis(
    [os.path.join(ROOT, "src", "main.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=[],
    # 依据 Lead 的版权要求：应用只分发 mascot + icons，
    # 不打包 assets/source（官方参考素材）与 assets/preview（文档预览图）。
    datas=[
        (os.path.join(ROOT, "assets", "mascot"), os.path.join("assets", "mascot")),
        (os.path.join(ROOT, "assets", "icons"), os.path.join("assets", "icons")),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
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
    [],
    exclude_binaries=True,
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
    icon=os.path.join(ROOT, "assets", "icons", "app.ico"),
    version=os.path.join(SPEC_DIR, "version_info_app.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
