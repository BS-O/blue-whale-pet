"""Windows 进程/窗口工具（QA 用）：PyInstaller onefile 的 GUI 在子进程里，
必须按进程树找窗口；单实例 Mutex 也要求测试结束彻底清理进程树。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.SetProcessDPIAware()

TH32CS_SNAPPROCESS = 0x00000002


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


def list_processes() -> list[dict]:
    out: list[dict] = []
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return out
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            out.append({"pid": entry.th32ProcessID, "ppid": entry.th32ParentProcessID,
                        "name": entry.szExeFile})
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return out


def family(root_pid: int) -> set[int]:
    """root 及其全部后代 pid。"""
    procs = list_processes()
    kids: dict[int, list[int]] = {}
    for p in procs:
        kids.setdefault(p["ppid"], []).append(p["pid"])
    seen, stack = set(), [root_pid]
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        stack.extend(kids.get(pid, []))
    return seen


def find_windows(pids: set[int], min_size: int = 30) -> list[dict]:
    out: list[dict] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value in pids and user32.IsWindowVisible(hwnd):
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            w, h = r.right - r.left, r.bottom - r.top
            if w > min_size and h > min_size:
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buf, 256)
                out.append({"hwnd": hwnd, "rect": [r.left, r.top, r.right, r.bottom], "title": buf.value})
        return True

    user32.EnumWindows(cb, 0)
    return out


def wait_windows(root_pid: int, timeout: float = 30.0, min_size: int = 30) -> list[dict]:
    t0 = time.time()
    while time.time() - t0 < timeout:
        wins = find_windows(family(root_pid), min_size)
        if wins:
            return wins
        time.sleep(0.25)
    return []


def kill_tree(root_pid: int) -> None:
    pids = family(root_pid)
    for pid in sorted(pids, reverse=True):
        sub = ctypes.windll.kernel32
        h = sub.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
        if h:
            sub.TerminateProcess(h, 0)
            sub.CloseHandle(h)
    # 二次兜底：按镜像名前缀（PyInstaller 子进程可能与父同名）
    time.sleep(0.3)


def kill_by_name(name_fragment: str) -> int:
    killed = 0
    for p in list_processes():
        if name_fragment.lower() in p["name"].lower() and p["pid"] != kernel32.GetCurrentProcessId():
            h = kernel32.OpenProcess(0x0001, False, p["pid"])
            if h:
                kernel32.TerminateProcess(h, 0)
                kernel32.CloseHandle(h)
                killed += 1
    return killed
