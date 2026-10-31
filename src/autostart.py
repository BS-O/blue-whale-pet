"""开机自启（SPEC §5）。

- Windows：``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`` 值名 ``BlueWhalePet``
- Linux：``~/.config/autostart/blue-whale-pet.desktop``
所有函数都不抛异常，失败返回 (False, 中文原因)。
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import constants as C
import resources

logger = logging.getLogger("bluewhale.autostart")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = C.APP_ID


def is_supported() -> bool:
    return sys.platform == "win32" or sys.platform.startswith("linux")


def _command_line() -> str:
    return resources.quote_command(resources.launch_command())


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def _win_is_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _type = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(str(value).strip())
    except FileNotFoundError:
        return False
    except OSError:
        logger.debug("读取自启注册项失败", exc_info=True)
        return False


def _win_set_enabled(enabled: bool) -> tuple[bool, str]:
    import winreg

    try:
        if enabled:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _command_line())
            logger.info("已设置开机自启: %s", _command_line())
            return True, "已开启开机自启"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass
        logger.info("已关闭开机自启")
        return True, "已关闭开机自启"
    except OSError as exc:
        logger.exception("设置开机自启失败")
        return False, f"设置开机自启失败：{exc}"


# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------

def _linux_desktop_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / f"{C.APP_PACKAGE}.desktop"


def _linux_is_enabled() -> bool:
    return _linux_desktop_path().is_file()


def _linux_set_enabled(enabled: bool) -> tuple[bool, str]:
    path = _linux_desktop_path()
    try:
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            command = " ".join(f'"{part}"' if " " in part else part for part in resources.launch_command())
            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={C.APP_NAME}\n"
                f"Comment={C.APP_SUBTITLE}\n"
                f"Exec={command}\n"
                f"Icon={C.APP_PACKAGE}\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n"
                "Categories=Utility;\n"
            )
            path.write_text(content, encoding="utf-8")
            logger.info("已写入自启项: %s", path)
            return True, "已开启开机自启"
        if path.exists():
            path.unlink()
        logger.info("已删除自启项: %s", path)
        return True, "已关闭开机自启"
    except OSError as exc:
        logger.exception("设置开机自启失败")
        return False, f"设置开机自启失败：{exc}"


# ---------------------------------------------------------------------------
# 统一接口
# ---------------------------------------------------------------------------

def is_enabled() -> bool:
    try:
        if sys.platform == "win32":
            return _win_is_enabled()
        if sys.platform.startswith("linux"):
            return _linux_is_enabled()
    except Exception:  # noqa: BLE001
        logger.debug("查询自启状态失败", exc_info=True)
    return False


def set_enabled(enabled: bool) -> tuple[bool, str]:
    try:
        if sys.platform == "win32":
            return _win_set_enabled(bool(enabled))
        if sys.platform.startswith("linux"):
            return _linux_set_enabled(bool(enabled))
        return False, "当前平台不支持开机自启"
    except Exception as exc:  # noqa: BLE001
        logger.exception("设置开机自启异常")
        return False, f"设置开机自启失败：{exc}"
