"""托盘管理器（跨平台封装）。

- Windows：原生 ctypes Shell_NotifyIcon（tray_win.WinTray），稳定、不阻塞 Tk 主线程
- Linux：可选 pystray（SPEC 允许可选）；不可用时返回 False，由宠物右键菜单兜底
- 菜单动作统一为 ``constants.Action`` id，投递到 Tk 主线程（queue + after）
"""
from __future__ import annotations

import logging
import sys
import threading
from typing import Any, Callable

import constants as C

logger = logging.getLogger("bluewhale.tray")


class TrayManager:
    def __init__(
        self,
        icon_path: str,
        on_action: Callable[[int], None],
        state_provider: Callable[[], dict[str, Any]],
        logger_: logging.Logger | None = None,
    ) -> None:
        self.icon_path = icon_path
        self.on_action = on_action
        self.state_provider = state_provider
        self.log = logger_ or logger
        self._impl: Any = None
        self.available = False
        self._linux_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    def start(self) -> bool:
        if sys.platform == "win32":
            return self._start_windows()
        if sys.platform.startswith("linux"):
            return self._start_linux()
        self.log.info("当前平台无托盘实现")
        return False

    def _start_windows(self) -> bool:
        try:
            from tray_win import WinTray

            impl = WinTray(
                self.icon_path,
                on_action=self.on_action,
                state_provider=self.state_provider,
                logger_=self.log,
            )
            if impl.start():
                self._impl = impl
                self.available = True
                self.log.info("Windows 托盘已启动")
                return True
            self.log.warning("Windows 托盘启动失败，使用宠物右键菜单兜底")
            return False
        except Exception:  # noqa: BLE001
            self.log.exception("Windows 托盘初始化异常")
            return False

    def _start_linux(self) -> bool:
        """可选 pystray；任何失败都只记录日志。"""
        try:
            import pystray  # type: ignore[import-not-found]
            from PIL import Image
        except Exception:  # noqa: BLE001
            self.log.info("pystray 不可用，Linux 使用宠物右键菜单兜底")
            return False
        try:
            image = Image.open(self.icon_path).convert("RGBA")
            image = image.resize((64, 64), Image.LANCZOS)

            def _checked(name: str) -> Callable[[Any], bool]:
                def _inner(_item: Any) -> bool:
                    try:
                        return bool((self.state_provider() or {}).get(name))
                    except Exception:  # noqa: BLE001
                        return False

                return _inner

            menu = pystray.Menu(
                pystray.MenuItem("和蓝鲸聊天", lambda *_: self._emit(C.Action.CHAT), default=True),
                pystray.MenuItem("设置…", lambda *_: self._emit(C.Action.SETTINGS)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("显示 / 隐藏桌宠", lambda *_: self._emit(C.Action.TOGGLE_SHOW)),
                pystray.MenuItem(
                    "窗口置顶", lambda *_: self._emit(C.Action.TOGGLE_TOP), checked=_checked("always_on_top")
                ),
                pystray.MenuItem(
                    "开机自启", lambda *_: self._emit(C.Action.TOGGLE_AUTOSTART), checked=_checked("autostart")
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("关于蓝鲸桌宠", lambda *_: self._emit(C.Action.ABOUT)),
                pystray.MenuItem("退出", lambda *_: self._emit(C.Action.QUIT)),
            )
            icon = pystray.Icon(C.APP_PACKAGE, image, C.TRAY_TOOLTIP, menu)

            def _run() -> None:
                try:
                    icon.run()
                except Exception:  # noqa: BLE001
                    self.log.warning("pystray 运行失败，托盘不可用")

            thread = threading.Thread(target=_run, name="BlueWhaleTrayLinux", daemon=True)
            thread.start()
            self._impl = icon
            self._linux_thread = thread
            self.available = True
            self.log.info("Linux pystray 托盘已启动")
            return True
        except Exception:  # noqa: BLE001
            self.log.exception("Linux 托盘初始化异常")
            return False

    def _emit(self, action_id: int) -> None:
        try:
            self.on_action(int(action_id))
        except Exception:  # noqa: BLE001
            self.log.exception("托盘动作回调异常")

    # ------------------------------------------------------------------
    def stop(self) -> None:
        impl = self._impl
        self._impl = None
        if impl is None:
            self.available = False
            return
        try:
            if sys.platform == "win32":
                impl.stop()
            else:
                impl.stop()
        except Exception:  # noqa: BLE001
            self.log.debug("停止托盘异常", exc_info=True)
        self.available = False


def notify(title: str, message: str) -> bool:
    """Windows 气泡通知（可选，暂未使用；保留接口）。"""
    return False
