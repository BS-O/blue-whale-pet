"""Linux 平台适配：ctypes XShape 异形窗口（无 python-xlib 依赖）。

- 用 Pillow 的 alpha 通道生成 1bit mask，经 libX11 + libXext 的 XShapeCombineMask 剪裁
- 对 Toplevel 及其 Canvas 子窗口分别应用（Tk 的 canvas 是独立 X 窗口，且位于 (0,0)）
- 安装 X 错误处理器：BadWindow 等 X 错误只记录不崩溃（默认处理器会直接终止进程）
- 任何一步失败都返回 False，由调用方回退 ``-alpha``，绝不崩溃
- 非 Linux 平台全部 no-op
"""
from __future__ import annotations

import ctypes
import ctypes.util
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("bluewhale.platform_linux")

IS_LINUX = sys.platform.startswith("linux")

ShapeBounding = 0
ShapeSet = 0
ShapeClip = 1

# 注意：Linux 上必须用 CFUNCTYPE（WINFUNCTYPE 仅 Windows 存在）
XERROR_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
_X_ERROR_REF: Any = None


def _ignore_x_error(_display: Any, _event: Any) -> int:
    """X 错误处理器：记录但不终止进程（默认 handler 会直接 exit）。"""
    try:
        logger.debug("忽略 X11 错误（XShape 异步请求）")
    except Exception:  # noqa: BLE001
        pass
    return 0


class XShape:
    """X11 Shape 扩展封装（懒加载；失败后 available=False）。"""

    def __init__(self) -> None:
        self.available = False
        self._display: Any = None
        self._x11: Any = None
        self._xext: Any = None
        self._failed_reason = ""
        if IS_LINUX:
            self._init()

    def _init(self) -> None:
        global _X_ERROR_REF
        try:
            x11_name = ctypes.util.find_library("X11") or "libX11.so.6"
            xext_name = ctypes.util.find_library("Xext") or "libXext.so.6"
            self._x11 = ctypes.CDLL(x11_name)
            self._xext = ctypes.CDLL(xext_name)
            self._x11.XOpenDisplay.restype = ctypes.c_void_p
            self._x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            self._x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
            self._x11.XCreateBitmapFromData.restype = ctypes.c_ulong
            self._x11.XCreateBitmapFromData.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.c_void_p,
                ctypes.c_uint,
                ctypes.c_uint,
            ]
            self._x11.XFreePixmap.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            self._x11.XFlush.argtypes = [ctypes.c_void_p]
            self._x11.XDefaultRootWindow.restype = ctypes.c_ulong
            self._x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            self._x11.XSetErrorHandler.argtypes = [XERROR_HANDLER]
            self._x11.XSetErrorHandler.restype = ctypes.c_void_p
            self._xext.XShapeCombineMask.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_ulong,
                ctypes.c_int,
            ]
            display = self._x11.XOpenDisplay(None)
            if not display:
                self._failed_reason = "XOpenDisplay 失败（无 DISPLAY）"
                return
            self._display = ctypes.c_void_p(display)
            try:
                _X_ERROR_REF = XERROR_HANDLER(_ignore_x_error)
                self._x11.XSetErrorHandler(_X_ERROR_REF)
                logger.info("已安装 X11 错误处理器（XShape 失败不再崩溃）")
            except Exception:  # noqa: BLE001
                logger.debug("安装 X11 错误处理器失败", exc_info=True)
            self.available = True
        except OSError as exc:  # 缺少 libX11/libXext
            self._failed_reason = f"加载 X11 库失败: {exc}"
            logger.info("XShape 不可用: %s", self._failed_reason)
        except Exception as exc:  # noqa: BLE001
            self._failed_reason = str(exc)
            logger.info("XShape 初始化失败: %s", self._failed_reason)

    @property
    def reason(self) -> str:
        return self._failed_reason

    # ------------------------------------------------------------------
    def apply_mask(
        self,
        mask_bytes: bytes,
        width: int,
        height: int,
        widget: Any,
        top_widget: Any | None = None,
    ) -> bool:
        """把 1bit mask（alpha_to_mask_bytes 的输出）作为窗口形状应用。

        widget 为主显示窗口（Canvas），top_widget 为其 Toplevel。
        Canvas 位于 Toplevel 的 (0,0) 且与窗口同尺寸，因此两者使用同一 mask、零偏移，
        避免 XTranslateCoordinates（对未映射窗口会产生 BadWindow 致命错误）。
        返回是否成功应用。
        """
        if not self.available or self._display is None:
            return False
        if not mask_bytes or width <= 0 or height <= 0:
            return False
        try:
            if not self._window_ready(widget):
                return False
            data = ctypes.create_string_buffer(mask_bytes, len(mask_bytes))
            targets: list[int] = []
            main_window = self._xwindow_id(widget)
            if not main_window:
                return False
            targets.append(main_window)
            if top_widget is not None and self._window_ready(top_widget):
                top_window = self._xwindow_id(top_widget)
                if top_window and top_window != main_window:
                    targets.append(top_window)
            root = self._x11.XDefaultRootWindow(self._display)
            pixmap = self._x11.XCreateBitmapFromData(
                self._display, root, ctypes.cast(data, ctypes.c_void_p), width, height
            )
            if not pixmap:
                return False
            try:
                for window in targets:
                    self._xext.XShapeCombineMask(
                        self._display,
                        ctypes.c_ulong(window),
                        ShapeBounding,
                        0,
                        0,
                        ctypes.c_ulong(pixmap),
                        ShapeSet,
                    )
                self._x11.XFlush(self._display)
                return True
            finally:
                self._x11.XFreePixmap(self._display, ctypes.c_ulong(pixmap))
        except Exception:  # noqa: BLE001
            logger.debug("XShapeCombineMask 失败", exc_info=True)
            return False

    def clear(self, widget: Any, top_widget: Any | None = None) -> None:
        if not self.available or self._display is None:
            return
        try:
            for target in (top_widget, widget):
                if target is None or not self._window_ready(target):
                    continue
                xwin = self._xwindow_id(target)
                if xwin:
                    self._xext.XShapeCombineMask(
                        self._display, ctypes.c_ulong(xwin), ShapeBounding, 0, 0, ctypes.c_ulong(0), ShapeSet
                    )
            self._x11.XFlush(self._display)
        except Exception:  # noqa: BLE001
            logger.debug("清除 XShape 失败", exc_info=True)

    def set_net_wm_pid(self, widget: Any) -> None:
        """给窗口设置 _NET_WM_PID，便于 xdotool search --pid 定位（Tk 子 Toplevel 默认没有）。"""
        if not self.available or self._display is None:
            return
        try:
            if not widget.winfo_exists():
                return
            xwin = self._xwindow_id(widget)
            if not xwin:
                return
            self._x11.XInternAtom.restype = ctypes.c_ulong
            self._x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            atom = self._x11.XInternAtom(self._display, b"_NET_WM_PID", 0)
            if not atom:
                return
            pid_value = ctypes.c_ulong(os.getpid())
            self._x11.XChangeProperty.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.c_ulong,
                ctypes.c_ulong,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.c_int,
            ]
            self._x11.XChangeProperty(
                self._display,
                ctypes.c_ulong(xwin),
                ctypes.c_ulong(atom),
                ctypes.c_ulong(6),  # XA_CARDINAL
                32,
                0,  # PropModeReplace
                ctypes.byref(pid_value),
                1,
            )
            self._x11.XFlush(self._display)
        except Exception:  # noqa: BLE001
            logger.debug("设置 _NET_WM_PID 失败", exc_info=True)

    # ------------------------------------------------------------------
    @staticmethod
    def _window_ready(widget: Any) -> bool:
        """窗口必须已存在且已映射（避免对未映射/已销毁窗口发 X 请求）。"""
        try:
            return bool(widget.winfo_exists()) and bool(widget.winfo_viewable())
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _xwindow_id(widget: Any) -> int:
        try:
            return int(widget.winfo_id())
        except Exception:  # noqa: BLE001
            return 0

    def close(self) -> None:
        try:
            if self._display is not None and self._x11 is not None:
                self._x11.XCloseDisplay(self._display)
        except Exception:  # noqa: BLE001
            pass
        self._display = None
        self.available = False


def virtual_screen_rect() -> tuple[int, int, int, int] | None:
    """Linux 下返回 None，由 Tk 屏幕尺寸兜底。"""
    return None


def set_window_title(widget: Any, title: str) -> bool:
    return False


def set_click_through(widget: Any, enabled: bool) -> bool:  # noqa: ARG001
    return False


def get_cursor_pos() -> tuple[int, int] | None:
    return None


def get_working_set_mb() -> float | None:
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024.0, 2)
    except (OSError, ValueError, IndexError):
        pass
    return None


def apply_tk_scaling(root: Any) -> float:
    return 1.0


def prepare_dpi() -> float:
    return 1.0


def dpi_scale() -> float:
    return 1.0


def get_root_hwnd(widget: Any) -> int:  # noqa: ARG001
    return 0


def set_foreground(widget: Any) -> None:
    try:
        widget.lift()
        widget.focus_force()
    except Exception:  # noqa: BLE001
        pass


def show_error_dialog(title: str, text: str) -> None:
    try:
        sys.stderr.write(f"{title}: {text}\n")
        sys.stderr.flush()
    except Exception:  # noqa: BLE001
        pass


def find_cjk_font() -> Path | None:
    """尽力找一个可用的中文字体文件（可选）。"""
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        p = Path(candidate)
        if p.is_file():
            return p
    return None
