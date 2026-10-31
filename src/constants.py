"""蓝鲸桌宠 - 全局常量（应用元信息、限制、契约必备列表）。

本模块不依赖任何第三方库，可被所有其他模块安全导入。
"""
from __future__ import annotations

APP_NAME = "蓝鲸桌宠"
APP_NAME_EN = "BlueWhalePet"
APP_VERSION = "1.0.0"
APP_SUBTITLE = "蓝色大肥鱼 / DeepSeek 桌宠"
APP_ID = "BlueWhalePet"
APP_PACKAGE = "blue-whale-pet"
APP_AUTHOR = "BlueWhalePet"
APP_DESCRIPTION = "基于 DeepSeek 蓝色大肥鱼形象的桌面宠物"

# Windows 色键（与资产描边兼容，manifest 缺省值）
DEFAULT_KEY_COLOR = "#010203"
DEFAULT_KEY_RGB = (1, 2, 3)

# 桌宠尺寸范围与默认值（SPEC §5）
MIN_SIZE = 64
MAX_SIZE = 320
DEFAULT_SIZE = 168

# Windows / Linux 托盘、窗口类名
TRAY_TOOLTIP = "蓝鲸桌宠 · 蓝色大肥鱼"
TRAY_WINDOW_CLASS = "BlueWhalePetTrayWnd"
PET_WINDOW_TITLE = APP_NAME
WM_CLASS = "blue-whale-pet"

# 自动睡眠、气泡等默认值
DEFAULT_BUBBLE_SECONDS = 7
DEFAULT_MAX_CHARS = 60
DEFAULT_AUTO_SLEEP_SECONDS = 180
CONTEXT_ROUNDS = 8

# 资产契约（SPEC §4.1）：14 个必需 state
REQUIRED_STATES = (
    "idle",
    "blink",
    "happy",
    "laugh",
    "talk",
    "think",
    "sleep",
    "surprise",
    "sad",
    "angry",
    "love",
    "drag",
    "wave",
    "eat",
)

# DeepSeek 现役模型名（默认 + 可选，设置窗口允许自定义）
DEFAULT_MODEL = "deepseek-flash"
MODEL_CHOICES = ("deepseek-flash", "deepseek-v4-pro")
DEFAULT_BASE_URL = "https://api.deepseek.com"

# 日志
LOG_MAX_BYTES = 1024 * 1024
LOG_BACKUP_COUNT = 2

# 托盘 / 右键菜单动作 id（Windows 原生菜单与 Tk 菜单共用语义）
class Action:
    CHAT = 1001
    SETTINGS = 1002
    TOGGLE_SHOW = 1003
    TOGGLE_TOP = 1004
    TOGGLE_AUTOSTART = 1005
    ABOUT = 1006
    QUIT = 1007
    SIZE_SMALL = 1101
    SIZE_MEDIUM = 1102
    SIZE_LARGE = 1103
    SIZE_DEFAULT = 1104
    TOGGLE_CLICK_THROUGH = 1008

SIZE_PRESETS = (
    ("小", 112),
    ("中", 168),
    ("大", 240),
)
