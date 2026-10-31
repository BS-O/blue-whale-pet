"""Windows 原生托盘（ctypes Shell_NotifyIcon + TrackPopupMenu，不使用 pystray/pywin32）。

- 独立消息循环线程 + 隐藏窗口接收托盘回调
- 处理 ``TaskbarCreated`` 广播（explorer 重启后重新注册图标）
- 右键弹出 Win32 PopupMenu（中文菜单项，含勾选状态），菜单动作投递到 Tk 主线程
- 退出时 ``NIM_DELETE``，不留幽灵图标
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
from typing import Any, Callable

import constants as C

logger = logging.getLogger("bluewhale.tray_win")

IS_WINDOWS = sys.platform == "win32"

# ---- 基础类型 -------------------------------------------------------------
DWORD = ctypes.c_ulong
UINT = ctypes.c_uint
BOOL = ctypes.c_int
HWND = ctypes.c_void_p
HANDLE = ctypes.c_void_p
HICON = ctypes.c_void_p
HMENU = ctypes.c_void_p
HINSTANCE = ctypes.c_void_p
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)

WM_APP = 0x8000
WM_NULL = 0x0000
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_CONTEXTMENU = 0x007B
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIM_SETVERSION = 0x00000004
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
MF_POPUP = 0x00000010
MF_GRAYED = 0x00000001

TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040
IDI_APPLICATION = 32512


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", HWND),
        ("message", UINT),
        ("wParam", WPARAM),
        ("lParam", LPARAM),
        ("time", DWORD),
        ("pt", ctypes.c_long * 2),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", DWORD),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", DWORD),
        ("hWnd", HWND),
        ("uID", UINT),
        ("uFlags", UINT),
        ("uCallbackMessage", UINT),
        ("hIcon", HICON),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", DWORD),
        ("dwStateMask", DWORD),
        ("szInfo", ctypes.c_wchar * 256),
        ("uTimeoutOrVersion", UINT),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", HICON),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", HINSTANCE),
        ("hIcon", HICON),
        ("hCursor", HANDLE),
        ("hbrBackground", HANDLE),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
    ]


class _WinApi:
    """延迟绑定 Win32 DLL，导入本模块时即使缺库也不崩。"""

    def __init__(self) -> None:
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._setup()

    def _setup(self) -> None:
        u = self.user32
        u.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        u.RegisterClassW.restype = ctypes.c_ushort
        u.UnregisterClassW.argtypes = [ctypes.c_wchar_p, HINSTANCE]
        u.UnregisterClassW.restype = BOOL
        u.CreateWindowExW.argtypes = [
            DWORD,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            HWND,
            HMENU,
            HINSTANCE,
            ctypes.c_void_p,
        ]
        u.CreateWindowExW.restype = HWND
        u.DestroyWindow.argtypes = [HWND]
        u.DestroyWindow.restype = BOOL
        u.DefWindowProcW.argtypes = [HWND, UINT, WPARAM, LPARAM]
        u.DefWindowProcW.restype = LRESULT
        u.GetMessageW.argtypes = [ctypes.POINTER(MSG), HWND, UINT, UINT]
        u.GetMessageW.restype = BOOL
        u.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
        u.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
        u.DispatchMessageW.restype = LRESULT
        u.PostMessageW.argtypes = [HWND, UINT, WPARAM, LPARAM]
        u.PostMessageW.restype = BOOL
        u.PostQuitMessage.argtypes = [ctypes.c_int]
        u.PostQuitMessage.restype = None
        u.RegisterWindowMessageW.argtypes = [ctypes.c_wchar_p]
        u.RegisterWindowMessageW.restype = UINT
        u.LoadImageW.argtypes = [HINSTANCE, ctypes.c_wchar_p, UINT, ctypes.c_int, ctypes.c_int, UINT]
        u.LoadImageW.restype = HICON
        u.LoadIconW.argtypes = [HINSTANCE, ctypes.c_void_p]
        u.LoadIconW.restype = HICON
        u.DestroyIcon.argtypes = [HICON]
        u.DestroyIcon.restype = BOOL
        u.CreatePopupMenu.argtypes = []
        u.CreatePopupMenu.restype = HMENU
        u.DestroyMenu.argtypes = [HMENU]
        u.DestroyMenu.restype = BOOL
        u.AppendMenuW.argtypes = [HMENU, UINT, ctypes.c_size_t, ctypes.c_wchar_p]
        u.AppendMenuW.restype = BOOL
        u.TrackPopupMenu.argtypes = [HMENU, UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, HWND, ctypes.c_void_p]
        u.TrackPopupMenu.restype = ctypes.c_int
        u.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
        u.GetCursorPos.restype = BOOL
        u.SetForegroundWindow.argtypes = [HWND]
        u.SetForegroundWindow.restype = BOOL
        u.GetSystemMetrics.argtypes = [ctypes.c_int]
        u.GetSystemMetrics.restype = ctypes.c_int
        k = self.kernel32
        k.CloseHandle.argtypes = [HANDLE]
        k.CloseHandle.restype = BOOL
        k.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        k.GetModuleHandleW.restype = HINSTANCE
        s = self.shell32
        s.Shell_NotifyIconW.argtypes = [DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
        s.Shell_NotifyIconW.restype = BOOL


_API: _WinApi | None = None


def _api() -> _WinApi:
    global _API
    if _API is None:
        _API = _WinApi()
    return _API


class WinTray:
    """Windows 原生托盘图标 + 右键菜单。"""

    def __init__(
        self,
        icon_path: str | os.PathLike[str],
        on_action: Callable[[int], None],
        state_provider: Callable[[], dict[str, Any]],
        logger_: logging.Logger | None = None,
        tooltip: str = C.TRAY_TOOLTIP,
    ) -> None:
        self.icon_path = str(icon_path)
        self.on_action = on_action
        self.state_provider = state_provider
        self.log = logger_ or logger
        self.tooltip = (tooltip or C.TRAY_TOOLTIP)[:127]
        self.hwnd: int | None = None
        self.available = False
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._init_error: str = ""
        self._callback_msg = WM_APP + 21
        self._taskbar_created = 0
        self._nid: NOTIFYICONDATAW | None = None
        self._icon: int | None = None
        self._class_name = f"{C.TRAY_WINDOW_CLASS}_{os.getpid()}"
        self._wndproc = WNDPROC(self._handle_message)  # 必须保持引用
        self._mutex = threading.Lock()
        self._deleted = False
        self._quitting = False

    # ------------------------------------------------------------------
    def start(self, timeout: float = 3.0) -> bool:
        if not IS_WINDOWS:
            return False
        try:
            _api()
        except Exception as exc:  # noqa: BLE001
            self._init_error = str(exc)
            self.log.warning("Win32 API 初始化失败: %s", exc)
            return False
        self._thread = threading.Thread(target=self._run, name="BlueWhaleTray", daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        if self._init_error:
            self.log.warning("托盘初始化失败: %s", self._init_error)
        return self.available

    def stop(self, timeout: float = 3.0) -> None:
        self._quitting = True
        hwnd = self.hwnd
        if hwnd:
            try:
                _api().user32.PostMessageW(HWND(hwnd), WM_CLOSE, 0, 0)
            except Exception:  # noqa: BLE001
                self.log.debug("发送托盘 WM_CLOSE 失败", exc_info=True)
        if self._thread is not None and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout)
        self.available = False
        self.hwnd = None

    # ------------------------------------------------------------------
    def _run(self) -> None:
        try:
            api = _api()
            u = api.user32
            hinstance = api.kernel32.GetModuleHandleW(None)
            wc = WNDCLASSW()
            wc.style = 0
            wc.lpfnWndProc = self._wndproc
            wc.cbClsExtra = 0
            wc.cbWndExtra = 0
            wc.hInstance = hinstance
            wc.hIcon = None
            wc.hCursor = None
            wc.hbrBackground = None
            wc.lpszMenuName = None
            wc.lpszClassName = self._class_name
            atom = u.RegisterClassW(ctypes.byref(wc))
            if not atom:
                self._fail(f"RegisterClassW 失败 err={ctypes.get_last_error()}")
                return
            self._taskbar_created = int(u.RegisterWindowMessageW("TaskbarCreated"))
            hwnd = u.CreateWindowExW(
                0, self._class_name, C.APP_NAME_EN, 0, 0, 0, 0, 0, None, None, hinstance, None
            )
            if not hwnd:
                self._fail(f"CreateWindowExW 失败 err={ctypes.get_last_error()}")
                u.UnregisterClassW(self._class_name, hinstance)
                return
            self.hwnd = int(hwnd)
            self._icon = self._load_icon(api)
            if not self._add_icon(api):
                self._fail(f"Shell_NotifyIcon 添加失败 err={ctypes.get_last_error()}")
                self._cleanup(api, hinstance, destroy_window=True)
                return
            self.available = True
            self._ready.set()
            msg = MSG()
            while True:
                result = u.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result == 0:  # WM_QUIT
                    break
                if result == -1:
                    self.log.warning("托盘消息循环 GetMessage 返回 -1")
                    break
                u.TranslateMessage(ctypes.byref(msg))
                u.DispatchMessageW(ctypes.byref(msg))
            self.log.info("托盘消息循环退出")
        except Exception as exc:  # noqa: BLE001
            self.log.exception("托盘线程异常")
            self._fail(str(exc))
        finally:
            try:
                api = _api()
                self._cleanup(api, api.kernel32.GetModuleHandleW(None), destroy_window=False)
            except Exception:  # noqa: BLE001
                pass
            self.available = False
            self._ready.set()

    def _fail(self, message: str) -> None:
        self._init_error = message
        self.available = False
        self._ready.set()

    # ------------------------------------------------------------------
    def _load_icon(self, api: _WinApi) -> int | None:
        u = api.user32
        try:
            if self.icon_path and os.path.exists(self.icon_path):
                icon = u.LoadImageW(None, self.icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
                if icon:
                    return int(icon)
        except Exception:  # noqa: BLE001
            self.log.debug("LoadImageW 失败", exc_info=True)
        try:
            icon = u.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
            if icon:
                return int(icon)
        except Exception:  # noqa: BLE001
            pass
        self.log.warning("无法加载托盘图标，使用无图标托盘项")
        return None

    def _make_nid(self) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = HWND(self.hwnd)
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_TIP | (NIF_ICON if self._icon else 0)
        nid.uCallbackMessage = self._callback_msg
        nid.hIcon = HICON(self._icon) if self._icon else None
        nid.szTip = self.tooltip
        return nid

    def _add_icon(self, api: _WinApi) -> bool:
        try:
            nid = self._make_nid()
            ok = bool(api.shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)))
            if ok:
                self._nid = nid
                self._deleted = False
            return ok
        except Exception:  # noqa: BLE001
            self.log.exception("添加托盘图标异常")
            return False

    def _delete_icon(self, api: _WinApi) -> None:
        if self._nid is not None and not self._deleted:
            try:
                api.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            except Exception:  # noqa: BLE001
                pass
            self._deleted = True

    def _cleanup(self, api: _WinApi, hinstance: Any, destroy_window: bool) -> None:
        self._delete_icon(api)
        try:
            if self._icon:
                api.user32.DestroyIcon(HICON(self._icon))
        except Exception:  # noqa: BLE001
            pass
        self._icon = None
        if self.hwnd:
            try:
                if destroy_window:
                    api.user32.DestroyWindow(HWND(self.hwnd))
            except Exception:  # noqa: BLE001
                pass
        try:
            api.user32.UnregisterClassW(self._class_name, hinstance)
        except Exception:  # noqa: BLE001
            pass
        self._nid = None
        self.hwnd = None

    # ------------------------------------------------------------------
    def _handle_message(self, hwnd: Any, msg: int, wparam: int, lparam: int) -> int:
        try:
            api = _api()
            u = api.user32
            if msg == self._callback_msg:
                event = int(lparam) & 0xFFFF
                if event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self._show_menu(int(hwnd) if hwnd else 0)
                elif event == WM_LBUTTONDBLCLK:
                    self._emit(C.Action.TOGGLE_SHOW)
                return 0
            if self._taskbar_created and msg == self._taskbar_created:
                self.log.info("收到 TaskbarCreated，重新注册托盘图标")
                self._delete_icon(api)
                self._add_icon(api)
                return 0
            if msg == WM_COMMAND:
                menu_id = int(wparam) & 0xFFFF
                if menu_id:
                    self._emit(menu_id)
                return 0
            if msg == WM_CLOSE:
                self._delete_icon(api)
                if hwnd:
                    u.DestroyWindow(HWND(int(hwnd)))
                return 0
            if msg == WM_DESTROY:
                u.PostQuitMessage(0)
                return 0
        except Exception:  # noqa: BLE001
            self.log.exception("WndProc 异常")
        try:
            return int(_api().user32.DefWindowProcW(HWND(int(hwnd)) if hwnd else None, msg, wparam, lparam))
        except Exception:  # noqa: BLE001
            return 0

    def _emit(self, action_id: int) -> None:
        try:
            self.on_action(int(action_id))
        except Exception:  # noqa: BLE001
            self.log.exception("托盘动作回调异常 action=%s", action_id)

    # ------------------------------------------------------------------
    def _show_menu(self, hwnd: int) -> None:
        if not hwnd:
            return
        api = _api()
        u = api.user32
        try:
            state = self.state_provider() or {}
        except Exception:  # noqa: BLE001
            self.log.exception("读取托盘菜单状态失败")
            state = {}
        menu = u.CreatePopupMenu()
        if not menu:
            return
        try:
            self._append(u, menu, MF_STRING, C.Action.CHAT, "和大肥鱼聊天")
            self._append(u, menu, MF_STRING, C.Action.SETTINGS, "设置…")
            self._append(u, menu, MF_SEPARATOR, 0, None)
            self._append(u, menu, MF_STRING, C.Action.TOGGLE_SHOW, "显示 / 隐藏桌宠")
            # 大小子菜单
            sub = u.CreatePopupMenu()
            current_size = int(state.get("size") or 0)
            if sub:
                for label, value in C.SIZE_PRESETS:
                    flags = MF_STRING | (MF_CHECKED if current_size == value else 0)
                    self._append(u, sub, flags, value, f"{label}（{value}px）")
                self._append(u, menu, MF_POPUP, int(sub), "大小")
            self._append(
                u,
                menu,
                MF_STRING | (MF_CHECKED if state.get("always_on_top") else 0),
                C.Action.TOGGLE_TOP,
                "窗口置顶",
            )
            self._append(
                u,
                menu,
                MF_STRING | (MF_CHECKED if state.get("click_through") else 0),
                C.Action.TOGGLE_CLICK_THROUGH,
                "鼠标穿透（仅托盘可操作）",
            )
            self._append(
                u,
                menu,
                MF_STRING | (MF_CHECKED if state.get("autostart") else 0),
                C.Action.TOGGLE_AUTOSTART,
                "开机自启",
            )
            self._append(u, menu, MF_SEPARATOR, 0, None)
            self._append(u, menu, MF_STRING, C.Action.ABOUT, "关于蓝色大肥鱼")
            self._append(u, menu, MF_STRING, C.Action.QUIT, "退出")
            point = POINT()
            u.GetCursorPos(ctypes.byref(point))
            u.SetForegroundWindow(HWND(hwnd))
            command = int(
                u.TrackPopupMenu(
                    menu,
                    TPM_RIGHTBUTTON | TPM_RETURNCMD,
                    int(point.x),
                    int(point.y),
                    0,
                    HWND(hwnd),
                    None,
                )
            )
            try:
                u.PostMessageW(HWND(hwnd), WM_NULL, 0, 0)
            except Exception:  # noqa: BLE001
                pass
            if command:
                self._emit(command)
        except Exception:  # noqa: BLE001
            self.log.exception("显示托盘菜单失败")
        finally:
            try:
                u.DestroyMenu(menu)
            except Exception:  # noqa: BLE001
                pass

    def _append(self, u: Any, menu: int, flags: int, item_id: int, text: str | None) -> None:
        try:
            u.AppendMenuW(menu, flags, ctypes.c_size_t(item_id), text)
        except Exception:  # noqa: BLE001
            self.log.debug("AppendMenuW 失败 flags=%s id=%s", flags, item_id, exc_info=True)
