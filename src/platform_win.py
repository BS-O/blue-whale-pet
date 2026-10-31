"""Windows 平台适配（ctypes，无 pywin32）：DPI、分层透明、点击穿透、内存读数。

所有函数在非 Windows 上安全降级（返回默认值 / no-op）。
"""
from __future__ import annotations

import ctypes
import logging
import sys
from typing import Any

logger = logging.getLogger("bluewhale.platform_win")

IS_WINDOWS = sys.platform == "win32"
_scale: float = 1.0
_scale_ready = False

# 常量
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
LWA_COLORKEY = 0x00000001
LWA_ALPHA = 0x00000002
GA_ROOT = 2
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79


def _user32() -> Any:
    return ctypes.windll.user32


def _kernel32() -> Any:
    return ctypes.windll.kernel32


# ---------------------------------------------------------------------------
# DPI
# ---------------------------------------------------------------------------

def prepare_dpi() -> float:
    """进程 DPI 感知 + 返回系统缩放（1.0 = 96dpi，1.25 = 125%）。

    必须在创建 Tk 之前调用。失败回退到非感知（scale=1.0），不抛异常。
    """
    global _scale, _scale_ready
    if not IS_WINDOWS:
        _scale, _scale_ready = 1.0, True
        return 1.0
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        set_awareness = shcore.SetProcessDpiAwareness
        set_awareness.argtypes = [ctypes.c_int]
        set_awareness.restype = ctypes.c_long
        if int(set_awareness(2)) != 0:  # PROCESS_PER_MONITOR_DPI_AWARE
            set_awareness(1)  # PROCESS_SYSTEM_DPI_AWARE
    except Exception:  # noqa: BLE001
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass
    try:
        _scale = float(_user32().GetDpiForSystem()) / 96.0
    except Exception:  # noqa: BLE001
        try:
            gdi32 = ctypes.windll.gdi32
            hdc = _user32().GetDC(0)
            dpi = int(gdi32.GetDeviceCaps(hdc, 88))  # LOGPIXELSX
            _user32().ReleaseDC(0, hdc)
            _scale = dpi / 96.0
        except Exception:  # noqa: BLE001
            _scale = 1.0
    if not (0.5 <= _scale <= 4.0):
        _scale = 1.0
    _scale_ready = True
    logger.info("DPI 感知完成: scale=%.3f", _scale)
    return _scale


def dpi_scale() -> float:
    if not _scale_ready:
        return prepare_dpi() if IS_WINDOWS else 1.0
    return _scale


def apply_tk_scaling(root: Any) -> float:
    """设置 Tk 字体缩放（pixels per point = dpi/72），让 10pt 字号在 125% 下正常。"""
    scale = dpi_scale()
    try:
        root.tk.call("tk", "scaling", 96.0 * scale / 72.0)
    except Exception:  # noqa: BLE001
        logger.debug("设置 tk scaling 失败", exc_info=True)
    return scale


# ---------------------------------------------------------------------------
# 窗口句柄 / 分层透明 / 点击穿透
# ---------------------------------------------------------------------------

def get_root_hwnd(widget: Any) -> int:
    """从 Tk widget 取真实顶层 HWND（GetAncestor GA_ROOT）。"""
    if not IS_WINDOWS:
        return 0
    try:
        hwnd = int(widget.winfo_id())
    except Exception:  # noqa: BLE001
        return 0
    try:
        user32 = _user32()
        user32.GetAncestor.restype = ctypes.c_void_p
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        ancestor = user32.GetAncestor(ctypes.c_void_p(hwnd), GA_ROOT)
        return int(ancestor) if ancestor else hwnd
    except Exception:  # noqa: BLE001
        return hwnd


def get_window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    if not IS_WINDOWS or not hwnd:
        return None
    try:
        rect = (ctypes.c_long * 4)()
        if _user32().GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect)):
            return int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])
    except Exception:  # noqa: BLE001
        pass
    return None


def set_window_title(widget: Any, title: str) -> bool:
    if not IS_WINDOWS:
        return False
    hwnd = get_root_hwnd(widget)
    if not hwnd:
        return False
    try:
        _user32().SetWindowTextW(ctypes.c_void_p(hwnd), ctypes.c_wchar_p(title))
        return True
    except Exception:  # noqa: BLE001
        return False


def _set_ex_style(hwnd: int, ex_style: int) -> bool:
    try:
        user32 = _user32()
        if hasattr(user32, "SetWindowLongPtrW"):
            setter = user32.SetWindowLongPtrW
            setter.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_longlong]
            setter.restype = ctypes.c_longlong
        else:
            setter = user32.SetWindowLongW
            setter.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
            setter.restype = ctypes.c_long
        setter(ctypes.c_void_p(hwnd), GWL_EXSTYLE, ex_style)
        return True
    except Exception:  # noqa: BLE001
        logger.debug("设置扩展窗口样式失败", exc_info=True)
        return False


def _get_ex_style(hwnd: int) -> int:
    try:
        user32 = _user32()
        if hasattr(user32, "GetWindowLongPtrW"):
            getter = user32.GetWindowLongPtrW
            getter.argtypes = [ctypes.c_void_p, ctypes.c_int]
            getter.restype = ctypes.c_longlong
        else:
            getter = user32.GetWindowLongW
            getter.argtypes = [ctypes.c_void_p, ctypes.c_int]
            getter.restype = ctypes.c_long
        return int(getter(ctypes.c_void_p(hwnd), GWL_EXSTYLE))
    except Exception:  # noqa: BLE001
        return 0


def apply_layered(hwnd: int, key_rgb: tuple[int, int, int], opacity: float = 1.0) -> bool:
    """色键 + 整窗 alpha 同时生效（覆盖 Tk 只能二选一的限制）。"""
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        ex = _get_ex_style(hwnd)
        if not (ex & WS_EX_LAYERED):
            _set_ex_style(hwnd, ex | WS_EX_LAYERED)
        r, g, b = key_rgb
        colorref = (r & 0xFF) | ((g & 0xFF) << 8) | ((b & 0xFF) << 16)
        alpha_byte = max(1, min(255, int(round(opacity * 255))))
        user32 = _user32()
        user32.SetLayeredWindowAttributes.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_ubyte,
            ctypes.c_uint32,
        ]
        user32.SetLayeredWindowAttributes.restype = ctypes.c_int
        ok = user32.SetLayeredWindowAttributes(
            ctypes.c_void_p(hwnd),
            ctypes.c_uint32(colorref),
            ctypes.c_ubyte(alpha_byte),
            ctypes.c_uint32(LWA_COLORKEY | LWA_ALPHA),
        )
        return bool(ok)
    except Exception:  # noqa: BLE001
        logger.debug("设置分层窗口属性失败", exc_info=True)
        return False


def set_click_through(hwnd: int, enabled: bool) -> bool:
    """设置/取消鼠标穿透（仅 Windows）。"""
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        ex = _get_ex_style(hwnd)
        new_ex = (ex | WS_EX_LAYERED | WS_EX_TRANSPARENT) if enabled else (ex & ~WS_EX_TRANSPARENT)
        if new_ex == ex:
            return True
        if not _set_ex_style(hwnd, new_ex):
            return False
        try:
            _user32().SetWindowPos(
                ctypes.c_void_p(hwnd),
                ctypes.c_void_p(0),
                0,
                0,
                0,
                0,
                0x0002 | 0x0001 | 0x0004 | 0x0020,  # NOMOVE|NOSIZE|NOZORDER|FRAMECHANGED
            )
        except Exception:  # noqa: BLE001
            pass
        return True
    except Exception:  # noqa: BLE001
        return False


def virtual_screen_rect() -> tuple[int, int, int, int] | None:
    """Windows 虚拟屏幕（多显示器）物理像素矩形；失败返回 None。"""
    if not IS_WINDOWS:
        return None
    try:
        user32 = _user32()
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int
        x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        if w > 0 and h > 0:
            return x, y, w, h
    except Exception:  # noqa: BLE001
        pass
    return None


# ---------------------------------------------------------------------------
# 内存
# ---------------------------------------------------------------------------

class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def get_working_set_mb() -> float | None:
    """当前进程 Working Set（MB）。Windows 用 psapi；Linux 读 /proc。"""
    if IS_WINDOWS:
        try:
            counters = _PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            psapi = ctypes.windll.psapi
            kernel32 = _kernel32()
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            process = kernel32.GetCurrentProcess()
            ok = psapi.GetProcessMemoryInfo(
                ctypes.c_void_p(process), ctypes.byref(counters), ctypes.sizeof(counters)
            )
            if ok:
                return round(counters.WorkingSetSize / (1024 * 1024), 2)
        except Exception:  # noqa: BLE001
            return None
        return None
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024.0, 2)
    except (OSError, ValueError, IndexError):
        pass
    return None


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def get_cursor_pos() -> tuple[int, int] | None:
    """当前鼠标物理屏幕坐标（GetCursorPos）。

    拖动窗口时 Tk 的 ``event.x_root/y_root`` 可能因窗口几何尚未刷新而漂移，
    用真实光标坐标计算位移更稳定。
    """
    if not IS_WINDOWS:
        return None
    try:
        point = _POINT()
        if _user32().GetCursorPos(ctypes.byref(point)):
            return int(point.x), int(point.y)
    except Exception:  # noqa: BLE001
        pass
    return None


def set_foreground(widget: Any) -> None:
    """把窗口提到前台（用于二次启动唤醒/聊天输入）。"""
    if not IS_WINDOWS:
        try:
            widget.lift()
            widget.focus_force()
        except Exception:  # noqa: BLE001
            pass
        return
    try:
        hwnd = get_root_hwnd(widget)
        if hwnd:
            _user32().SetForegroundWindow(ctypes.c_void_p(hwnd))
    except Exception:  # noqa: BLE001
        pass


def show_error_dialog(title: str, text: str) -> None:
    """启动失败时弹一个系统错误框（windowed exe 无 stdout 时可见）。"""
    if IS_WINDOWS:
        try:
            ctypes.windll.user32.MessageBoxW(None, str(text), str(title), 0x00000010)
            return
        except Exception:  # noqa: BLE001
            pass
    try:
        sys.stderr.write(f"{title}: {text}\n")
        sys.stderr.flush()
    except Exception:  # noqa: BLE001
        pass
