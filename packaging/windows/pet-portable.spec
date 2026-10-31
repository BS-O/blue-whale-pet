# -*- mode: python ; coding: utf-8 -*-
"""蓝色大肥鱼 Windows 便携版（PyInstaller onefile，windowed）。

构建（从任意目录）：
    py -m PyInstaller --noconfirm --clean \
        --distpath E:\\pet-build-tmp\\dist --workpath E:\\pet-build-tmp\\work\\portable \
        packaging\\windows\\pet-portable.spec
产物：dist/BlueWhalePet.exe（由 build_all.ps1 复制为
      release/windows/BlueWhalePet-Portable-1.0.0.exe）

关键契约（SPEC §3 / §7.1）：
  * onefile + windowed（无控制台）；
  * icon = assets/icons/app.ico，assets/ 作为 datas 打入 _MEIPASS/assets；
  * packaging/windows/portable.flag 打入 _MEIPASS 根 → 运行时 is_portable() 为真。
QA 专用：设置环境变量 PET_BUILD_CONSOLE=1 可构建「控制台版」自检程序
（仅用于捕获 windowed 版无法输出的 --version/--selftest stdout，不随交付）。
"""
import os

APP_NAME = "BlueWhalePet"
APP_VERSION = "1.0.0"

SPEC_DIR = os.path.abspath(globals().get("SPECPATH") or os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.abspath(os.path.join(SPEC_DIR, "..", ".."))
CONSOLE = os.environ.get("PET_BUILD_CONSOLE", "") == "1"

# tkinter / Pillow 是运行时硬依赖；源码里的延迟 import 需要 hiddenimports 兜底。
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
        (os.path.join(SPEC_DIR, "portable.flag"), "."),
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
    console=CONSOLE,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "assets", "icons", "app.ico"),
    version=os.path.join(SPEC_DIR, "version_info_app.txt"),
)
