#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蓝色大肥鱼（BlueWhalePet）Windows 自研安装器。

设计约束（见 SPEC §7.1）：
  * 纯 Python + tkinter 实现，零外部打包工具依赖（无 Inno Setup / NSIS / 7z）；
  * PyInstaller onefile + windowed 构建，载荷 = onedir 应用目录的 payload.zip
    （构建时通过 --add-data 嵌入，运行时从 sys._MEIPASS 解压）；
  * 安装到 %LOCALAPPDATA%\\Programs\\BlueWhalePet（无需管理员）；
  * 中文向导：欢迎 / 许可 / 目录 / 快捷方式 / 进度 / 完成；
  * 开始菜单快捷方式必建，桌面快捷方式默认不建（勾选才建，静默默认不建）；
  * HKCU 卸载注册项 + 安装器自身复制为 uninstall.exe；
  * 命令行：/S 静默安装、/D=路径 自定义目录、/uninstall /S 静默卸载，
    可选 /DESKTOP（静默时也建桌面快捷方式）、/RUN（安装后运行）；
  * 卸载清理安装目录 / 开始菜单 / 桌面快捷方式 / HKCU Uninstall / Run 自启项，
    保留 %APPDATA%\\BlueWhalePet 用户配置（含 config.json、日志等）。
  * 所有关键动作写入 %TEMP%\\BlueWhalePet-setup.log，便于 QA 在 windowed
    exe 无控制台输出时核查；退出码：0 成功，1 用户取消，2 失败。

注意：本文件只允许出现在 packaging/windows/installer/（pack-win 写入范围）。
"""
from __future__ import annotations

import ctypes
import datetime
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
APP_NAME = "蓝色大肥鱼"
APP_NAME_EN = "BlueWhalePet"
APP_VERSION = "1.0.0"
APP_EXE = "BlueWhalePet.exe"
UNINSTALL_EXE = "uninstall.exe"
PUBLISHER = "BlueWhalePet Project"
DISPLAY_ICON_NAME = "BlueWhalePet.ico"

START_MENU_LNK_NAME = "蓝色大肥鱼.lnk"
DESKTOP_LNK_NAME = "蓝色大肥鱼.lnk"

REG_UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\BlueWhalePet"
REG_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "BlueWhalePet"

LOG_PATH = os.path.join(tempfile.gettempdir(), "BlueWhalePet-setup.log")

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008

FOLDERID_DESKTOP = "B4BFCC3A-DB2C-424C-B029-7FE99A87C641"
FOLDERID_PROGRAMS = "A77F5D77-2E2B-44C3-A6A2-ABA601054A51"
FOLDERID_LOCALAPPDATA = "F1B32785-6FBA-4FCF-9D55-7B8E7F157091"

LICENSE_TEXT = """\
蓝色大肥鱼（BlueWhalePet） 1.0.0  软件许可协议

1. 代码许可
   本项目源代码采用 MIT 许可证发布。你可以自由使用、修改、分发本软件，
   但需保留版权声明与许可声明。本软件按“现状”提供，不附带任何明示或
   默示担保。

2. 美术资产与商标
   本软件中的“蓝色大肥鱼 / 蓝鲸”形象基于 DeepSeek 官方标志进行非官方
   二次创作；DeepSeek 名称与蓝鲸标志的相关权利归 DeepSeek 所有。
   本项目为非官方个人桌面宠物项目，与 DeepSeek 官方无隶属关系，
   仅供个人学习与娱乐使用，不得用于商业用途。

3. 数据与隐私
   * 本软件不会在未经你操作的情况下上传任何文件；
   * API Key 仅保存在你本机的配置文件中（%APPDATA%\\BlueWhalePet 或
     便携版 exe 同级 BlueWhalePet-Data 目录），不会随安装包分发；
   * 仅当你主动发起聊天时，对话文本才会发送到你配置的 DeepSeek API。

4. 免责声明
   使用本软件产生的任何直接或间接后果由使用者自行承担。
   安装本软件即表示你已阅读并同意上述条款。
"""

WELCOME_TEXT = (
    "欢迎安装 蓝色大肥鱼 1.0.0（蓝色大肥鱼 / DeepSeek 桌宠）。\n\n"
    "安装程序将把程序文件复制到你的用户目录，并创建开始菜单快捷方式。\n"
    "整个安装过程无需管理员权限，也不会修改系统级设置。\n\n"
    "点击“下一步”继续。"
)

# ---------------------------------------------------------------------------
# 基础工具：日志 / 子进程 / 资源
# ---------------------------------------------------------------------------
_log_lock = threading.Lock()


def log(message: str) -> None:
    """把日志追加到 %TEMP%\\BlueWhalePet-setup.log（windowed 无控制台时靠它排查）。"""
    try:
        line = "[%s] %s\n" % (
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            str(message),
        )
        with _log_lock:
            with open(LOG_PATH, "a", encoding="utf-8", errors="replace") as fh:
                fh.write(line)
    except Exception:
        pass


def init_log() -> None:
    try:
        with open(LOG_PATH, "w", encoding="utf-8", errors="replace") as fh:
            fh.write("BlueWhalePet installer %s\n" % APP_VERSION)
            fh.write("time=%s\n" % datetime.datetime.now().isoformat(timespec="seconds"))
            fh.write("argv=%r\n" % (sys.argv,))
            fh.write("frozen=%r executable=%r\n" % (getattr(sys, "frozen", False), sys.executable))
            fh.write("---\n")
    except Exception:
        pass


def resource_path(name: str):
    """安装器内嵌资源路径（PyInstaller onefile：sys._MEIPASS；源码模式：本目录）。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidate = os.path.join(base, name)
        if os.path.exists(candidate):
            return candidate
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(here, name)
    if os.path.exists(candidate):
        return candidate
    return None


def _hidden_flags():
    return CREATE_NO_WINDOW if os.name == "nt" else 0


def run_hidden(args, timeout=120, cwd=None, env=None):
    """静默执行子进程（不闪黑框），返回 CompletedProcess。"""
    return subprocess.run(
        args,
        capture_output=True,
        timeout=timeout,
        cwd=cwd,
        env=env,
        creationflags=_hidden_flags(),
    )


def _powershell_exe() -> str:
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    cand = os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    if os.path.isfile(cand):
        return cand
    found = shutil.which("powershell") or shutil.which("powershell.exe")
    return found or "powershell.exe"


# ---------------------------------------------------------------------------
# 已知文件夹（正确处理 OneDrive 重定向的桌面 / 开始菜单）
# ---------------------------------------------------------------------------
class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid_from_string(text: str) -> "_GUID":
    raw = uuid.UUID(text).bytes_le
    guid = _GUID()
    guid.Data1 = int.from_bytes(raw[0:4], "little")
    guid.Data2 = int.from_bytes(raw[4:6], "little")
    guid.Data3 = int.from_bytes(raw[6:8], "little")
    for i in range(8):
        guid.Data4[i] = raw[8 + i]
    return guid


def known_folder(guid_string: str, fallback: str) -> Path:
    if os.name == "nt":
        try:
            shell32 = ctypes.windll.shell32
            ole32 = ctypes.windll.ole32
            shell32.SHGetKnownFolderPath.argtypes = [
                ctypes.POINTER(_GUID),
                ctypes.c_ulong,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_wchar_p),
            ]
            shell32.SHGetKnownFolderPath.restype = ctypes.c_long
            ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
            ole32.CoTaskMemFree.restype = None
            guid = _guid_from_string(guid_string)
            out = ctypes.c_wchar_p()
            hr = shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out))
            if hr == 0 and out.value:
                path = Path(out.value)
                ole32.CoTaskMemFree(out)
                if path.is_dir():
                    return path
        except Exception:
            log("known_folder(%s) 失败: %s" % (guid_string, traceback.format_exc(limit=1)))
    return Path(fallback)


def local_appdata_dir() -> Path:
    env = os.environ.get("LOCALAPPDATA")
    fallback = str(Path(os.environ.get("USERPROFILE", str(Path.home()))) / "AppData" / "Local")
    return known_folder(FOLDERID_LOCALAPPDATA, env or fallback)


def desktop_dir() -> Path:
    env = os.environ.get("USERPROFILE")
    fallback = str(Path(env) / "Desktop") if env else str(Path.home() / "Desktop")
    return known_folder(FOLDERID_DESKTOP, fallback)


def start_menu_programs_dir() -> Path:
    appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    fallback = str(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return known_folder(FOLDERID_PROGRAMS, fallback)


def default_install_dir() -> Path:
    return local_appdata_dir() / "Programs" / APP_NAME_EN


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------
def _winreg():
    import winreg  # noqa: WPS433 - 仅 Windows
    return winreg


def read_reg_value(root, path, name):
    winreg = _winreg()
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return value
    except OSError:
        return None


def read_install_location():
    try:
        winreg = _winreg()
        value = read_reg_value(winreg.HKEY_CURRENT_USER, REG_UNINSTALL, "InstallLocation")
        return Path(value) if value else None
    except Exception:
        return None


def write_uninstall_entry(install_dir: Path) -> None:
    winreg = _winreg()
    exe_path = install_dir / APP_EXE
    uninstall_path = install_dir / UNINSTALL_EXE
    icon_path = install_dir / DISPLAY_ICON_NAME
    install_date = datetime.datetime.now().strftime("%Y%m%d")

    # 估算占用空间（KB）
    total = 0
    for root_dir, _dirs, files in os.walk(install_dir):
        for filename in files:
            try:
                total += os.path.getsize(os.path.join(root_dir, filename))
            except OSError:
                pass
    size_kb = max(1, int(total / 1024))

    values = [
        ("DisplayName", winreg.REG_SZ, APP_NAME),
        ("DisplayVersion", winreg.REG_SZ, APP_VERSION),
        ("Publisher", winreg.REG_SZ, PUBLISHER),
        ("DisplayIcon", winreg.REG_SZ, str(icon_path) if icon_path.is_file() else str(exe_path)),
        ("UninstallString", winreg.REG_SZ, '"%s" /uninstall' % uninstall_path),
        ("QuietUninstallString", winreg.REG_SZ, '"%s" /uninstall /S' % uninstall_path),
        ("InstallLocation", winreg.REG_SZ, str(install_dir)),
        ("InstallDate", winreg.REG_SZ, install_date),
        ("EstimatedSize", winreg.REG_DWORD, size_kb),
        ("NoModify", winreg.REG_DWORD, 1),
        ("NoRepair", winreg.REG_DWORD, 1),
        ("URLInfoAbout", winreg.REG_SZ, "https://api.deepseek.com"),
        ("Comments", winreg.REG_SZ, "%s %s 非官方桌面宠物；DeepSeek 蓝鲸形象版权归 DeepSeek。" % (APP_NAME, APP_VERSION)),
    ]
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_UNINSTALL, 0, winreg.KEY_WRITE) as key:
        for name, kind, value in values:
            winreg.SetValueEx(key, name, 0, kind, value)
    log("注册表写入完成: HKCU\\%s (EstimatedSize=%d KB)" % (REG_UNINSTALL, size_kb))


def remove_uninstall_entry() -> None:
    winreg = _winreg()
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_UNINSTALL)
        log("已删除注册表项 HKCU\\%s" % REG_UNINSTALL)
    except OSError as exc:
        log("删除注册表项（可能不存在）: %s" % exc)


def remove_run_entries(install_dir: Path) -> None:
    """删除 HKCU Run 自启项（精确名 + 指向安装目录的值），覆盖 pet-core 写入的自启项。"""
    winreg = _winreg()
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE)
    except OSError:
        return
    removed = []
    with key:
        idx = 0
        names = []
        while True:
            try:
                name, value, _kind = winreg.EnumValue(key, idx)
            except OSError:
                break
            names.append((name, value))
            idx += 1
        target = str(install_dir).lower()
        for name, value in names:
            drop = name.lower() == RUN_VALUE_NAME.lower()
            if not drop and isinstance(value, str):
                norm = value.lower().replace("/", "\\")
                if target and target in norm:
                    drop = True
            if drop:
                try:
                    winreg.DeleteValue(key, name)
                    removed.append(name)
                except OSError as exc:
                    log("删除 Run 值失败 %s: %s" % (name, exc))
    if removed:
        log("已删除 Run 自启项: %s" % ", ".join(removed))
    else:
        log("未发现需要删除的 Run 自启项")


# ---------------------------------------------------------------------------
# 快捷方式：优先 PowerShell WScript.Shell（中文路径安全），失败回退 ctypes COM
# ---------------------------------------------------------------------------
def _ps_quote(text: str) -> str:
    return str(text).replace("'", "''")


def _create_shortcuts_via_powershell(shortcuts) -> bool:
    """shortcuts: list[dict(lnk, target, arguments, workdir, icon, description)]"""
    lines = [
        "$ErrorActionPreference = 'Stop'",
        "$ws = New-Object -ComObject WScript.Shell",
    ]
    for sc in shortcuts:
        lines.append("$s = $ws.CreateShortcut('%s')" % _ps_quote(sc["lnk"]))
        lines.append("$s.TargetPath = '%s'" % _ps_quote(sc["target"]))
        lines.append("$s.Arguments = '%s'" % _ps_quote(sc.get("arguments", "")))
        lines.append("$s.WorkingDirectory = '%s'" % _ps_quote(sc.get("workdir", "")))
        if sc.get("icon"):
            lines.append("$s.IconLocation = '%s,0'" % _ps_quote(sc["icon"]))
        lines.append("$s.Description = '%s'" % _ps_quote(sc.get("description", APP_NAME)))
        lines.append("$s.Save()")
        lines.append("$s = $null")
    script_path = os.path.join(tempfile.gettempdir(), "BlueWhalePet-lnk-%d.ps1" % os.getpid())
    try:
        with open(script_path, "w", encoding="utf-8-sig", newline="\r\n") as fh:
            fh.write("\r\n".join(lines) + "\r\n")
        result = run_hidden(
            [
                _powershell_exe(),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                script_path,
            ],
            timeout=90,
        )
        if result.returncode == 0:
            return all(Path(sc["lnk"]).is_file() for sc in shortcuts)
        log(
            "PowerShell 创建快捷方式失败 rc=%s stderr=%s"
            % (result.returncode, (result.stderr or b"").decode("mbcs", "replace")[:800])
        )
    except Exception:
        log("PowerShell 创建快捷方式异常: %s" % traceback.format_exc(limit=3))
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass
    return False


def _create_shortcut_via_com(sc) -> bool:
    """ctypes 直接调用 IShellLinkW / IPersistFile 创建 .lnk（PowerShell 不可用时的兜底）。"""
    if os.name != "nt":
        return False
    try:
        from ctypes import wintypes

        ole32 = ctypes.windll.ole32
        HRESULT = ctypes.c_long

        CLSID_ShellLink = _guid_from_string("00021401-0000-0000-C000-000000000046")
        IID_IShellLinkW = _guid_from_string("000214F9-0000-0000-C000-000000000046")
        IID_IPersistFile = _guid_from_string("0000010b-0000-0000-C000-000000000046")

        def com_call(obj, index, restype, argtypes, *args):
            vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p))[0]
            func_ptr = ctypes.cast(vtable, ctypes.POINTER(ctypes.c_void_p))[index]
            prototype = ctypes.WINFUNCTYPE(restype, *argtypes)
            return prototype(func_ptr)(obj, *args)

        ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
        try:
            punk = ctypes.c_void_p()
            hr = ole32.CoCreateInstance(
                ctypes.byref(CLSID_ShellLink),
                None,
                1,  # CLSCTX_INPROC_SERVER
                ctypes.byref(IID_IShellLinkW),
                ctypes.byref(punk),
            )
            if hr != 0 or not punk:
                log("CoCreateInstance(ShellLink) 失败 hr=%s" % hr)
                return False
            try:
                # IShellLinkW 方法序号：SetPath=20, SetWorkingDirectory=9, SetArguments=11,
                # SetDescription=7, SetIconLocation=17
                if sc.get("target"):
                    com_call(punk, 20, HRESULT, (ctypes.c_void_p, wintypes.LPCWSTR), str(sc["target"]))
                if sc.get("workdir"):
                    com_call(punk, 9, HRESULT, (ctypes.c_void_p, wintypes.LPCWSTR), str(sc["workdir"]))
                if sc.get("arguments"):
                    com_call(punk, 11, HRESULT, (ctypes.c_void_p, wintypes.LPCWSTR), str(sc["arguments"]))
                if sc.get("description"):
                    com_call(punk, 7, HRESULT, (ctypes.c_void_p, wintypes.LPCWSTR), str(sc["description"]))
                if sc.get("icon"):
                    com_call(
                        punk,
                        17,
                        HRESULT,
                        (ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_int),
                        str(sc["icon"]),
                        0,
                    )
                persist = ctypes.c_void_p()
                hr = com_call(
                    punk,
                    0,  # QueryInterface
                    HRESULT,
                    (ctypes.c_void_p, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)),
                    ctypes.byref(IID_IPersistFile),
                    ctypes.byref(persist),
                )
                if hr != 0 or not persist:
                    log("QueryInterface(IPersistFile) 失败 hr=%s" % hr)
                    return False
                try:
                    hr = com_call(
                        persist,
                        6,  # IPersistFile::Save（IPersistFile: IsDirty=4, Load=5, Save=6）
                        HRESULT,
                        (ctypes.c_void_p, wintypes.LPCWSTR, wintypes.BOOL),
                        str(sc["lnk"]),
                        1,
                    )
                    if hr != 0:
                        log("IPersistFile::Save 失败 hr=%s" % hr)
                        return False
                finally:
                    com_call(persist, 2, ctypes.c_ulong, (ctypes.c_void_p,))  # Release
            finally:
                com_call(punk, 2, ctypes.c_ulong, (ctypes.c_void_p,))  # Release
        finally:
            ole32.CoUninitialize()
        return Path(sc["lnk"]).is_file()
    except Exception:
        log("ctypes COM 创建快捷方式异常: %s" % traceback.format_exc(limit=3))
        return False


def create_shortcut(sc) -> bool:
    lnk = Path(sc["lnk"])
    try:
        lnk.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log("创建快捷方式父目录失败 %s: %s" % (lnk.parent, exc))
        return False
    if _create_shortcuts_via_powershell([sc]):
        log("快捷方式已创建（PowerShell）: %s" % lnk)
        return True
    log("PowerShell 方式失败，回退 ctypes COM: %s" % lnk)
    if _create_shortcut_via_com(sc):
        log("快捷方式已创建（ctypes COM）: %s" % lnk)
        return True
    log("ERROR: 快捷方式创建失败: %s" % lnk)
    return False


def remove_shortcut(path) -> None:
    path = Path(path)
    try:
        if path.is_file():
            path.unlink()
            log("已删除快捷方式: %s" % path)
    except OSError as exc:
        log("删除快捷方式失败 %s: %s" % (path, exc))


def app_shortcuts(install_dir: Path, with_desktop: bool):
    target = str(install_dir / APP_EXE)
    icon = str(install_dir / DISPLAY_ICON_NAME)
    scs = [
        {
            "lnk": str(start_menu_programs_dir() / START_MENU_LNK_NAME),
            "target": target,
            "arguments": "",
            "workdir": str(install_dir),
            "icon": icon,
            "description": APP_NAME,
        }
    ]
    if with_desktop:
        scs.append(
            {
                "lnk": str(desktop_dir() / DESKTOP_LNK_NAME),
                "target": target,
                "arguments": "",
                "workdir": str(install_dir),
                "icon": icon,
                "description": APP_NAME,
            }
        )
    return scs


# ---------------------------------------------------------------------------
# 应用进程控制 / 载荷解压 / 目录清理
# ---------------------------------------------------------------------------
def kill_running_app() -> None:
    try:
        result = run_hidden(["taskkill", "/IM", APP_EXE, "/F"], timeout=30)
        out = (result.stdout or b"") + (result.stderr or b"")
        log("taskkill %s rc=%s out=%s" % (APP_EXE, result.returncode, out.decode("mbcs", "replace").strip()[:300]))
        if result.returncode == 0:
            time.sleep(0.8)
    except Exception:
        log("结束应用进程失败（可能未运行）: %s" % traceback.format_exc(limit=1))


def payload_zip_path():
    path = resource_path("payload.zip")
    if not path or not os.path.isfile(path):
        return None
    return path


def _dir_size(path: Path) -> int:
    total = 0
    for root_dir, _dirs, files in os.walk(str(path)):
        for filename in files:
            try:
                total += os.path.getsize(os.path.join(root_dir, filename))
            except OSError:
                pass
    return total


def extract_payload(install_dir: Path, progress_cb) -> None:
    zip_path = payload_zip_path()
    if not zip_path:
        raise RuntimeError("安装器内部错误：找不到载荷 payload.zip")
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.infolist()
        total = len(members) or 1
        for index, member in enumerate(members, 1):
            zf.extract(member, str(install_dir))
            if index % 20 == 0 or index == total:
                progress_cb(10 + int(65 * index / total), "正在安装文件 %d/%d" % (index, total))
    app_exe = install_dir / APP_EXE
    if not app_exe.is_file():
        raise RuntimeError("安装失败：载荷解压后未找到 %s" % APP_EXE)
    progress_cb(76, "应用文件安装完成")


def find_app_icon(install_dir: Path):
    candidates = [
        install_dir / "assets" / "icons" / "app.ico",
        install_dir / "_internal" / "assets" / "icons" / "app.ico",
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    for root_dir, _dirs, files in os.walk(str(install_dir)):
        for filename in files:
            if filename.lower() == "app.ico":
                return Path(root_dir) / filename
    return None


def _cleanup_install_dir(install_dir: Path) -> None:
    """清空安装目录（保留 uninstall.exe，由延迟删除脚本处理整个目录）。"""
    if not install_dir.is_dir():
        return
    keep = {UNINSTALL_EXE.lower()}
    for child in os.scandir(str(install_dir)):
        if child.name.lower() in keep:
            continue
        try:
            if child.is_dir(follow_symlinks=False):
                shutil.rmtree(child.path, ignore_errors=True)
            else:
                try:
                    os.chmod(child.path, 0o666)
                except OSError:
                    pass
                os.remove(child.path)
        except OSError as exc:
            log("卸载清理文件失败 %s: %s" % (child.path, exc))


def _finalize_install_dir_removal(install_dir: Path) -> None:
    """移除安装目录（其中包含正在运行的 uninstall.exe）。

    1) Windows 允许重命名运行中的 exe：先尝试把 uninstall.exe 移出安装目录到
       %TEMP%，随后安装目录可立即删除，QA 在卸载进程退出后检查无残留；
    2) 无论第 1 步是否成功，都安排延迟 cmd 兜底：等待本进程与 onefile
       bootloader 退出后删除安装目录（带重试）与移出的临时副本。
    """
    running = Path(sys.executable)
    moved = None
    try:
        if (
            running.name.lower() == UNINSTALL_EXE
            and running.is_file()
            and running.parent.resolve() == install_dir.resolve()
        ):
            target = Path(tempfile.gettempdir()) / ("BlueWhalePet-uninstall-%d.exe" % os.getpid())
            os.replace(str(running), str(target))
            moved = target
            log("已把运行中的卸载程序移出安装目录: %s" % target)
    except OSError as exc:
        log("移动运行中的卸载程序失败（将使用延迟删除兜底）: %s" % exc)

    try:
        if install_dir.is_dir():
            shutil.rmtree(str(install_dir), ignore_errors=True)
    except OSError as exc:
        log("立即删除安装目录失败: %s" % exc)
    log("安装目录已删除=%s: %s" % (not install_dir.exists(), install_dir))

    # 延迟兜底清理（等待本进程与 bootloader 退出，释放文件锁）
    parts = ["ping 127.0.0.1 -n 2 >nul"]
    if moved is not None:
        parts.append('del /f /q "%s"' % moved)
    parts.append(
        'for /l %i in (1,1,45) do @(rmdir /s /q "%s" 2>nul & if not exist "%s" exit /b 0 & ping 127.0.0.1 -n 2 >nul)'
        % (install_dir, install_dir)
    )
    cmdline = " & ".join(parts)
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", cmdline],
            cwd=tempfile.gettempdir(),
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
            close_fds=True,
        )
        log("已安排延迟兜底清理: %s" % install_dir)
    except Exception:
        log("安排延迟清理失败: %s" % traceback.format_exc(limit=2))
        try:
            _spawn_delayed_rmdir_ps(install_dir)
        except Exception:
            pass


def _spawn_delayed_rmdir_ps(directory: Path) -> None:
    script = os.path.join(tempfile.gettempdir(), "BlueWhalePet-cleanup-%d.ps1" % os.getpid())
    text = (
        "$ErrorActionPreference = 'SilentlyContinue'\r\n"
        "Start-Sleep -Seconds 2\r\n"
        "Remove-Item -LiteralPath '%s' -Recurse -Force\r\n"
        "Remove-Item -LiteralPath '%s' -Force\r\n" % (_ps_quote(str(directory)), _ps_quote(script))
    )
    with open(script, "w", encoding="utf-8-sig", newline="\r\n") as fh:
        fh.write(text)
    subprocess.Popen(
        [
            _powershell_exe(),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            script,
        ],
        cwd=tempfile.gettempdir(),
        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
        close_fds=True,
    )
    log("已安排 PowerShell 延迟删除安装目录: %s" % directory)


# ---------------------------------------------------------------------------
# 安装 / 卸载核心逻辑
# ---------------------------------------------------------------------------
def _normalize_install_dir(raw) -> Path:
    if raw:
        candidate = Path(os.path.expandvars(str(raw).strip().strip('"').strip("'")))
        if not candidate.is_absolute():
            candidate = Path(os.path.abspath(str(candidate)))
        return candidate
    return default_install_dir()


def _dir_is_ours_or_empty(path: Path) -> bool:
    if not path.exists():
        return True
    if not path.is_dir():
        return False
    try:
        entries = list(os.scandir(str(path)))
    except OSError:
        return False
    if not entries:
        return True
    return any(entry.name.lower() == APP_EXE.lower() for entry in entries)


def perform_install(install_dir: Path, with_desktop: bool, progress_cb) -> None:
    log("开始安装到: %s (桌面快捷方式=%s)" % (install_dir, with_desktop))
    progress_cb(3, "正在检查安装环境…")

    if not _dir_is_ours_or_empty(install_dir):
        raise RuntimeError(
            "目标目录已存在且不是蓝色大肥鱼的安装目录，请换一个空目录：\n%s" % install_dir
        )

    install_dir.mkdir(parents=True, exist_ok=True)

    progress_cb(6, "正在结束正在运行的蓝色大肥鱼…")
    kill_running_app()

    # 覆盖安装时先清理旧文件（保留 uninstall.exe 由后续复制覆盖）
    for child in os.scandir(str(install_dir)):
        if child.name.lower() == UNINSTALL_EXE.lower():
            continue
        try:
            if child.is_dir(follow_symlinks=False):
                shutil.rmtree(child.path, ignore_errors=True)
            else:
                os.remove(child.path)
        except OSError as exc:
            log("覆盖安装清理旧文件失败 %s: %s" % (child.path, exc))

    progress_cb(10, "正在解压应用文件…")
    extract_payload(install_dir, progress_cb)

    progress_cb(78, "正在安装图标…")
    icon_src = find_app_icon(install_dir)
    if icon_src is not None:
        try:
            shutil.copy2(str(icon_src), str(install_dir / DISPLAY_ICON_NAME))
            log("已安装图标: %s" % (install_dir / DISPLAY_ICON_NAME))
        except OSError as exc:
            log("复制图标失败: %s" % exc)

    progress_cb(82, "正在安装卸载程序…")
    if getattr(sys, "frozen", False):
        try:
            shutil.copy2(sys.executable, str(install_dir / UNINSTALL_EXE))
            log("已复制卸载程序: %s" % (install_dir / UNINSTALL_EXE))
        except OSError as exc:
            raise RuntimeError("复制卸载程序失败: %s" % exc)
    else:
        log("WARNING: 源码模式运行，跳过复制 uninstall.exe（仅 PyInstaller 构建产物完整支持卸载）")

    progress_cb(87, "正在创建快捷方式…")
    shortcuts = app_shortcuts(install_dir, with_desktop)
    created = 0
    for sc in shortcuts:
        if create_shortcut(sc):
            created += 1
    if created != len(shortcuts):
        raise RuntimeError("快捷方式创建失败（%d/%d）" % (created, len(shortcuts)))

    progress_cb(93, "正在写入卸载信息…")
    write_uninstall_entry(install_dir)

    progress_cb(100, "安装完成")
    log("RESULT: INSTALL OK %s (files=%d bytes)" % (install_dir, _dir_size(install_dir)))


def _schedule_dir_removal(install_dir: Path) -> bool:
    """安排 detached cmd 稍后删除安装目录（本进程退出后执行，带重试）。

    不在本进程里删除文件：卸载程序自身与 PyInstaller bootloader 都还在
    安装目录中运行，边运行边删容易触发退出码异常（实测 -1）。交给
    独立 cmd 进程等待 1~2 秒后再删，既稳又不会失败。
    """
    target = str(install_dir)
    cmdline = (
        'ping 127.0.0.1 -n 2 >nul & '
        'for /l %i in (1,1,60) do @('
        'rmdir /s /q "' + target + '" 2>nul & '
        'if not exist "' + target + '" exit /b 0 & '
        'ping 127.0.0.1 -n 1 >nul)'
    )
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", cmdline],
            cwd=tempfile.gettempdir(),
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
            close_fds=True,
        )
        log("已安排退出后删除安装目录: %s" % install_dir)
        return True
    except Exception:
        log("安排删除安装目录失败: %s" % traceback.format_exc(limit=2))
        return False



def _mark_leftover_for_reboot(install_dir: Path) -> None:
    """把残留的 uninstall.exe / 空目录登记为"重启后删除"（MoveFileEx）。"""
    MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
    k32 = ctypes.windll.kernel32
    try:
        k32.MoveFileExW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        k32.MoveFileExW.restype = ctypes.c_int
    except Exception:
        pass
    leftovers = []
    try:
        leftovers = [p for p in install_dir.iterdir()]
    except OSError:
        return
    for item in leftovers:
        try:
            ok = k32.MoveFileExW(str(item), None, MOVEFILE_DELAY_UNTIL_REBOOT)
            log("登记重启删除 %s -> %s" % (item, bool(ok)))
        except Exception:
            log("登记重启删除失败 %s: %s" % (item, traceback.format_exc(limit=1)))
    try:
        ok = k32.MoveFileExW(str(install_dir), None, MOVEFILE_DELAY_UNTIL_REBOOT)
        log("登记重启删除目录 %s -> %s" % (install_dir, bool(ok)))
    except Exception:
        pass


def perform_uninstall(install_dir: Path, progress_cb, remove_user_data: bool = False) -> None:
    log("开始卸载: %s" % install_dir)
    progress_cb(5, "正在结束蓝色大肥鱼进程…")
    kill_running_app()

    progress_cb(25, "正在删除快捷方式…")
    remove_shortcut(start_menu_programs_dir() / START_MENU_LNK_NAME)
    remove_shortcut(desktop_dir() / DESKTOP_LNK_NAME)
    # 防御性清理英文名快捷方式（历史版本/手动创建）
    remove_shortcut(start_menu_programs_dir() / ("%s.lnk" % APP_NAME_EN))
    remove_shortcut(desktop_dir() / ("%s.lnk" % APP_NAME_EN))

    progress_cb(45, "正在清理注册表…")
    remove_run_entries(install_dir)
    remove_uninstall_entry()

    progress_cb(70, "正在删除安装文件…")
    # 顺序：① 先登记"退出后延迟删除"（正常桌面由独立 cmd 完成）
    #       ② 再尽力清理文件（卸载器自身无法删除正在运行的自己）
    #       ③ 若只剩 uninstall.exe，登记重启后删除，避免永久残留
    scheduled = _schedule_dir_removal(install_dir)
    try:
        _cleanup_install_dir(install_dir)
        _mark_leftover_for_reboot(install_dir)
        log("即时清理完成，目录仍存在=%s" % install_dir.exists())
    except Exception:
        log("即时清理出现异常（将由后台删除兜底）: %s" % traceback.format_exc(limit=3))

    progress_cb(100, "卸载完成")
    log("RESULT: UNINSTALL OK %s (delayed_cleanup=%s)" % (install_dir, scheduled))
    if remove_user_data:
        log("WARNING: remove_user_data 未实现（当前版本始终保留用户配置）")


# ---------------------------------------------------------------------------
# 命令行解析
# ---------------------------------------------------------------------------
def parse_args(argv):
    opts = {
        "silent": False,
        "uninstall": False,
        "dir": None,
        "desktop": False,
        "run": False,
        "help": False,
    }
    for raw in argv:
        arg = str(raw)
        low = arg.strip().lower()
        if low in ("/s", "-s", "/silent", "--silent", "/verysilent"):
            opts["silent"] = True
        elif low in ("/uninstall", "--uninstall", "-uninstall", "/u"):
            opts["uninstall"] = True
        elif low.startswith("/d=") or low.startswith("--dir="):
            opts["dir"] = arg.split("=", 1)[1].strip().strip('"').strip("'")
        elif low in ("/desktop", "--desktop", "/createdesktopicon"):
            opts["desktop"] = True
        elif low in ("/run", "--run", "/launch"):
            opts["run"] = True
        elif low in ("/help", "-h", "--help", "/?"):
            opts["help"] = True
        else:
            log("忽略未知参数: %r" % arg)
    return opts


# ---------------------------------------------------------------------------
# 简易 tkinter 向导
# ---------------------------------------------------------------------------
class WizardApp:
    """中文安装向导（欢迎/许可/目录/快捷方式/进度/完成）。"""

    PAGE_WELCOME = 0
    PAGE_LICENSE = 1
    PAGE_DIR = 2
    PAGE_OPTIONS = 3
    PAGE_PROGRESS = 4
    PAGE_FINISH = 5

    def __init__(self, options):
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox

        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.options = options
        self.result_code = 1
        self._images = []
        self._install_thread = None
        self._queue = queue.Queue()

        self.root = tk.Tk()
        self.root.title("蓝色大肥鱼 安装程序")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.cancel)
        ico = resource_path("setup.ico")
        if ico:
            try:
                self.root.iconbitmap(ico)
            except Exception:
                pass

        width, height = 700, 580
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 3)
        self.root.geometry("%dx%d+%d+%d" % (width, height, x, y))
        try:
            style = ttk.Style(self.root)
            if "vista" in style.theme_names():
                style.theme_use("vista")
            elif "clam" in style.theme_names():
                style.theme_use("clam")
        except Exception:
            pass

        bg = "#FFFFFF"
        self.root.configure(bg=bg)

        banner = resource_path("banner.png")
        if banner:
            try:
                image = tk.PhotoImage(master=self.root, file=banner)
                self._images.append(image)
                tk.Label(self.root, image=image, bd=0, bg=bg).place(x=50, y=12)
            except Exception:
                log("加载 banner.png 失败")
        tk.Frame(self.root, bg="#D9DEE8", height=1).place(x=24, y=182, width=652)

        side = resource_path("side.png")
        if side:
            try:
                image = tk.PhotoImage(master=self.root, file=side)
                self._images.append(image)
                tk.Label(self.root, image=image, bd=0, bg=bg).place(x=24, y=198)
            except Exception:
                log("加载 side.png 失败")

        self.container = tk.Frame(self.root, bg=bg)
        self.container.place(x=204, y=198, width=472, height=312)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.pages = []
        self._build_pages()

        self.button_bar = tk.Frame(self.root, bg=bg)
        self.button_bar.place(x=204, y=522, width=472, height=38)
        self.btn_cancel = ttk.Button(self.button_bar, text="取消", width=10, command=self.cancel)
        self.btn_back = ttk.Button(self.button_bar, text="< 上一步", width=10, command=self.go_back)
        self.btn_next = ttk.Button(self.button_bar, text="下一步 >", width=12, command=self.go_next)
        self.btn_cancel.pack(side="right", padx=(8, 0))
        self.btn_next.pack(side="right", padx=(8, 0))
        self.btn_back.pack(side="right")

        self.step = self.PAGE_WELCOME
        self._show_page(self.PAGE_WELCOME)
        self.root.after(80, self._poll_queue)

    # -- 页面构建 ---------------------------------------------------------
    def _page_frame(self):
        frame = self.tk.Frame(self.container, bg="#FFFFFF")
        frame.grid(row=0, column=0, sticky="nsew")
        self.pages.append(frame)
        return frame

    def _title(self, parent, text):
        label = self.tk.Label(
            parent,
            text=text,
            bg="#FFFFFF",
            fg="#0B1330",
            font=("Microsoft YaHei UI", 13, "bold"),
            anchor="w",
            justify="left",
        )
        label.pack(fill="x", pady=(2, 10))
        return label

    def _body(self, parent, text, **kwargs):
        label = self.tk.Label(
            parent,
            text=text,
            bg="#FFFFFF",
            fg="#243044",
            font=("Microsoft YaHei UI", 9),
            anchor="nw",
            justify="left",
            wraplength=440,
        )
        label.pack(fill="both", expand=True, **kwargs)
        return label

    def _build_pages(self):
        tk = self.tk
        # 0 欢迎
        page = self._page_frame()
        self._title(page, "欢迎使用 蓝色大肥鱼 安装程序")
        self._body(page, WELCOME_TEXT)

        # 1 许可
        page = self._page_frame()
        self._title(page, "许可协议")
        text = tk.Text(
            page,
            wrap="word",
            height=13,
            relief="solid",
            bd=1,
            bg="#F7F9FC",
            fg="#243044",
            font=("Microsoft YaHei UI", 8),
            padx=8,
            pady=6,
        )
        scroll = self.ttk.Scrollbar(page, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y", pady=(0, 4))
        text.pack(side="left", fill="both", expand=True, pady=(0, 4))
        text.insert("1.0", LICENSE_TEXT)
        text.configure(state="disabled")
        self.accept_var = tk.BooleanVar(value=False)
        self.accept_check = self.ttk.Checkbutton(
            page,
            text="我已阅读并接受上述许可协议",
            variable=self.accept_var,
            command=self._refresh_buttons,
        )
        self.accept_check.pack(anchor="w")

        # 2 目录
        page = self._page_frame()
        self._title(page, "选择安装位置")
        self._body(
            page,
            "蓝色大肥鱼将安装到下面的目录（默认按当前用户安装，无需管理员权限）：",
        )
        self.dir_var = tk.StringVar(value=str(default_install_dir()))
        entry_row = tk.Frame(page, bg="#FFFFFF")
        entry_row.pack(fill="x", pady=(2, 6))
        self.dir_entry = self.ttk.Entry(entry_row, textvariable=self.dir_var, width=54)
        self.dir_entry.pack(side="left", fill="x", expand=True)
        self.ttk.Button(entry_row, text="浏览…", width=8, command=self.browse_dir).pack(
            side="left", padx=(8, 0)
        )
        self.dir_hint = tk.Label(
            page,
            text="目录必须为空，或为已安装的蓝色大肥鱼旧版本（将被覆盖升级）。",
            bg="#FFFFFF",
            fg="#6B7686",
            font=("Microsoft YaHei UI", 8),
            anchor="w",
            justify="left",
            wraplength=440,
        )
        self.dir_hint.pack(fill="x", pady=(4, 0))

        # 3 快捷方式
        page = self._page_frame()
        self._title(page, "选择附加任务")
        self.desktop_var = tk.BooleanVar(value=False)
        self.ttk.Checkbutton(
            page,
            text="创建桌面快捷方式（默认不创建）",
            variable=self.desktop_var,
        ).pack(anchor="w", pady=(2, 4))
        self.ttk.Checkbutton(
            page,
            text="创建开始菜单快捷方式（总是创建）",
            state="disabled",
        ).pack(anchor="w")
        self._body(
            page,
            "安装完成后，可以从开始菜单「蓝色大肥鱼」启动程序。\n"
            "卸载程序会保留你的用户配置（%APPDATA%\\BlueWhalePet）。",
            pady=(16, 0),
        )

        # 4 进度
        page = self._page_frame()
        self._title(page, "正在安装")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = self.ttk.Progressbar(
            page, orient="horizontal", mode="determinate", maximum=100, variable=self.progress_var
        )
        self.progress_bar.pack(fill="x", pady=(8, 10))
        self.progress_label = tk.Label(
            page,
            text="准备安装…",
            bg="#FFFFFF",
            fg="#243044",
            font=("Microsoft YaHei UI", 9),
            anchor="w",
            justify="left",
            wraplength=440,
        )
        self.progress_label.pack(fill="x")

        # 5 完成
        page = self._page_frame()
        self._title(page, "安装完成")
        self.finish_label = tk.Label(
            page,
            text="",
            bg="#FFFFFF",
            fg="#243044",
            font=("Microsoft YaHei UI", 9),
            anchor="nw",
            justify="left",
            wraplength=440,
        )
        self.finish_label.pack(fill="x")
        self.run_var = tk.BooleanVar(value=True)
        self.run_check = self.ttk.Checkbutton(
            page, text="立即运行 蓝色大肥鱼", variable=self.run_var
        )
        self.run_check.pack(anchor="w", pady=(18, 0))

    # -- 导航 -------------------------------------------------------------
    def _show_page(self, step):
        self.step = step
        self.pages[step].tkraise()
        self._refresh_buttons()

    def _refresh_buttons(self):
        step = self.step
        if step in (self.PAGE_PROGRESS,):
            self.btn_back.pack_forget()
            self.btn_next.pack_forget()
            self.btn_cancel.configure(text="取消", state="disabled")
            return
        self.btn_cancel.configure(text="取消", state="normal")
        if step == self.PAGE_FINISH:
            self.btn_back.pack_forget()
            self.btn_next.pack_forget()
            self.btn_cancel.pack(side="right", padx=(8, 0))
            self.btn_cancel.configure(text="完成")
            return
        self.btn_cancel.pack(side="right", padx=(8, 0))
        if step == self.PAGE_WELCOME:
            self.btn_back.pack_forget()
        else:
            if not self.btn_back.winfo_ismapped():
                self.btn_back.pack(side="right")
        if not self.btn_next.winfo_ismapped():
            self.btn_next.pack(side="right", padx=(8, 0))
        if step == self.PAGE_LICENSE:
            self.btn_next.configure(text="下一步 >", state="normal" if self.accept_var.get() else "disabled")
        elif step == self.PAGE_OPTIONS:
            self.btn_next.configure(text="安装", state="normal")
        else:
            self.btn_next.configure(text="下一步 >", state="normal")

    def go_back(self):
        if self.step == self.PAGE_WELCOME:
            return
        self._show_page(self.step - 1)

    def browse_dir(self):
        initial = self.dir_var.get() or str(default_install_dir())
        chosen = self.filedialog.askdirectory(title="选择安装目录", initialdir=initial, mustexist=False)
        if chosen:
            self.dir_var.set(os.path.normpath(chosen))

    def go_next(self):
        if self.step == self.PAGE_LICENSE and not self.accept_var.get():
            return
        if self.step == self.PAGE_DIR:
            raw = self.dir_var.get().strip()
            if not raw:
                self.messagebox.showwarning("提示", "请选择安装目录。")
                return
            target = _normalize_install_dir(raw)
            self.dir_var.set(str(target))
            if not _dir_is_ours_or_empty(target):
                self.messagebox.showwarning(
                    "目录不可用",
                    "该目录已存在且不是蓝色大肥鱼的安装目录，请选择其他目录：\n%s" % target,
                )
                return
            try:
                target.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self.messagebox.showerror("目录不可写", "无法创建安装目录：\n%s\n\n%s" % (target, exc))
                return
        if self.step == self.PAGE_OPTIONS:
            self.start_install()
            return
        if self.step == self.PAGE_FINISH:
            self.finish()
            return
        self._show_page(self.step + 1)

    # -- 安装 worker ------------------------------------------------------
    def _progress(self, percent, message):
        self._queue.put(("progress", percent, message))

    def start_install(self):
        install_dir = _normalize_install_dir(self.dir_var.get())
        with_desktop = bool(self.desktop_var.get())
        self._show_page(self.PAGE_PROGRESS)
        self.progress_var.set(0)
        self.progress_label.configure(text="正在准备安装…")
        self._install_dir = install_dir

        def worker():
            try:
                perform_install(install_dir, with_desktop, self._progress)
                self._queue.put(("done", install_dir))
            except Exception as exc:
                log("安装失败: %s" % traceback.format_exc())
                self._queue.put(("error", str(exc)))

        self._install_thread = threading.Thread(target=worker, name="install-worker", daemon=True)
        self._install_thread.start()

    def _poll_queue(self):
        try:
            while True:
                item = self._queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    _kind, percent, message = item
                    self.progress_var.set(percent)
                    self.progress_label.configure(text=message)
                elif kind == "done":
                    install_dir = item[1]
                    self._install_dir = install_dir
                    self._show_page(self.PAGE_FINISH)
                    self.finish_label.configure(
                        text=(
                            "蓝色大肥鱼 1.0.0 已成功安装到：\n%s\n\n"
                            "你可以从开始菜单「蓝色大肥鱼」启动，或使用桌面快捷方式（如果已创建）。\n"
                            "卸载程序：%s\n\n"
                            "祝你玩得开心！🐳" % (install_dir, install_dir / UNINSTALL_EXE)
                        )
                    )
                    self.btn_cancel.configure(text="完成")
                elif kind == "error":
                    message = item[1]
                    log("向用户显示安装错误: %s" % message)
                    self.messagebox.showerror("安装失败", "安装过程中发生错误：\n\n%s\n\n详细信息见日志：\n%s" % (message, LOG_PATH))
                    self._show_page(self.PAGE_OPTIONS)
        except queue.Empty:
            pass
        except Exception:
            log("UI 队列处理异常: %s" % traceback.format_exc(limit=3))
        self.root.after(80, self._poll_queue)

    # -- 结束 -------------------------------------------------------------
    def finish(self):
        self.result_code = 0
        if self.run_var.get():
            try:
                install_dir = getattr(self, "_install_dir", None) or _normalize_install_dir(self.dir_var.get())
                exe = Path(install_dir) / APP_EXE
                if exe.is_file():
                    subprocess.Popen([str(exe)], cwd=str(exe.parent), creationflags=DETACHED_PROCESS)
                    log("安装完成页：已启动应用 %s" % exe)
            except Exception:
                log("启动应用失败: %s" % traceback.format_exc(limit=2))
        self.root.destroy()

    def cancel(self):
        if self.step == self.PAGE_PROGRESS:
            return
        if self.step in (self.PAGE_FINISH,):
            self.finish()
            return
        if self.messagebox.askyesno("确认取消", "确定要取消安装吗？"):
            self.result_code = 1
            self.root.destroy()

    def run(self):
        self.root.mainloop()
        return self.result_code


class UninstallApp:
    """简易卸载确认窗口（非静默卸载时使用）。"""

    def __init__(self, install_dir):
        import tkinter as tk
        from tkinter import ttk, messagebox

        self.tk = tk
        self.messagebox = messagebox
        self.install_dir = install_dir
        self.result_code = 1
        self._queue = queue.Queue()
        self._images = []

        self.root = tk.Tk()
        self.root.title("卸载 蓝色大肥鱼")
        self.root.resizable(False, False)
        self.root.configure(bg="#FFFFFF")
        ico = resource_path("setup.ico")
        if ico:
            try:
                self.root.iconbitmap(ico)
            except Exception:
                pass
        width, height = 620, 420
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 3)
        self.root.geometry("%dx%d+%d+%d" % (width, height, x, y))

        side = resource_path("side.png")
        if side:
            try:
                image = tk.PhotoImage(master=self.root, file=side)
                self._images.append(image)
                tk.Label(self.root, image=image, bd=0, bg="#FFFFFF").place(x=16, y=20)
            except Exception:
                pass

        tk.Label(
            self.root,
            text="卸载 蓝色大肥鱼",
            bg="#FFFFFF",
            fg="#0B1330",
            font=("Microsoft YaHei UI", 13, "bold"),
            anchor="w",
        ).place(x=204, y=24)
        tk.Label(
            self.root,
            text=(
                "将从下面的目录卸载蓝色大肥鱼：\n%s\n\n"
                "卸载会删除程序文件、开始菜单/桌面快捷方式、卸载注册项和开机自启项；\n"
                "你的用户配置（%%APPDATA%%\\BlueWhalePet）会被保留。\n\n"
                "确定要卸载吗？" % install_dir
            ),
            bg="#FFFFFF",
            fg="#243044",
            font=("Microsoft YaHei UI", 9),
            anchor="nw",
            justify="left",
            wraplength=380,
        ).place(x=204, y=64)

        self.status = tk.Label(
            self.root,
            text="",
            bg="#FFFFFF",
            fg="#243044",
            font=("Microsoft YaHei UI", 9),
            anchor="w",
            justify="left",
            wraplength=380,
        )
        self.status.place(x=204, y=286)
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress = ttk.Progressbar(
            self.root, orient="horizontal", mode="determinate", maximum=100, variable=self.progress_var
        )
        self.progress.place(x=204, y=322, width=380)
        self.btn = ttk.Button(self.root, text="卸载", width=12, command=self.start_uninstall)
        self.btn.place(x=204, y=360)
        self.close_btn = ttk.Button(self.root, text="取消", width=10, command=self.cancel)
        self.close_btn.place(x=344, y=360)
        self.root.protocol("WM_DELETE_WINDOW", self.cancel)
        self._done = False
        self.root.after(80, self._poll)

    def _progress(self, percent, message):
        self._queue.put(("progress", percent, message))

    def start_uninstall(self):
        self.btn.configure(state="disabled")
        self.close_btn.configure(state="disabled")

        def worker():
            try:
                perform_uninstall(self.install_dir, self._progress)
                self._queue.put(("done", None))
            except Exception as exc:
                log("卸载失败: %s" % traceback.format_exc())
                self._queue.put(("error", str(exc)))

        threading.Thread(target=worker, name="uninstall-worker", daemon=True).start()

    def _poll(self):
        try:
            while True:
                item = self._queue.get_nowait()
                if item[0] == "progress":
                    self.progress_var.set(item[1])
                    self.status.configure(text=item[2])
                elif item[0] == "done":
                    self._done = True
                    self.progress_var.set(100)
                    self.status.configure(text="卸载完成。感谢使用 蓝色大肥鱼！")
                    self.btn.configure(text="关闭", state="normal", command=self.finish)
                    self.close_btn.configure(state="disabled", command=self.finish)
                    self.result_code = 0
                elif item[0] == "error":
                    self.messagebox.showerror("卸载失败", "卸载过程中发生错误：\n\n%s\n\n日志：%s" % (item[1], LOG_PATH))
                    self.btn.configure(state="normal")
                    self.close_btn.configure(state="normal")
        except queue.Empty:
            pass
        except Exception:
            log("卸载 UI 队列异常: %s" % traceback.format_exc(limit=3))
        self.root.after(80, self._poll)

    def cancel(self):
        if self._done:
            self.finish()
            return
        self.result_code = 1
        self.root.destroy()

    def finish(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()
        return self.result_code


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def resolve_uninstall_dir(options) -> Path:
    raw = options.get("dir")
    if raw:
        return _normalize_install_dir(raw)
    registered = read_install_location()
    if registered and registered.is_dir():
        return registered
    # 正处于安装目录内的 uninstall.exe：安装目录 = 自身所在目录
    try:
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / APP_EXE).is_file():
            return exe_dir
        if (Path(sys.argv[0]).resolve().parent / APP_EXE).is_file():
            return Path(sys.argv[0]).resolve().parent
    except Exception:
        pass
    return default_install_dir()


def run_silent(options) -> int:
    try:
        if options["uninstall"]:
            install_dir = resolve_uninstall_dir(options)
            perform_uninstall(install_dir, lambda pct, msg: log("[%d%%] %s" % (pct, msg)))
        else:
            install_dir = _normalize_install_dir(options.get("dir"))
            perform_install(
                install_dir,
                bool(options.get("desktop")),
                lambda pct, msg: log("[%d%%] %s" % (pct, msg)),
            )
        return 0
    except Exception as exc:
        log("SILENT FAILED: %s" % traceback.format_exc())
        return 2


def run_gui(options) -> int:
    try:
        if options["uninstall"]:
            install_dir = resolve_uninstall_dir(options)
            if not install_dir.is_dir():
                log("GUI 卸载：安装目录不存在 %s" % install_dir)
            return UninstallApp(install_dir).run()
        app = WizardApp(options)
        return app.run()
    except Exception:
        log("GUI 初始化失败: %s" % traceback.format_exc())
        return 2


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    init_log()
    options = parse_args(argv)
    log(
        "options: silent=%s uninstall=%s dir=%r desktop=%s run=%s"
        % (
            options["silent"],
            options["uninstall"],
            options["dir"],
            options["desktop"],
            options["run"],
        )
    )
    if os.name != "nt":
        log("仅支持 Windows")
        return 2
    if options["help"]:
        return 0
    if options["silent"]:
        code = run_silent(options)
        log("exit code=%d" % code)
        return code
    code = run_gui(options)
    log("exit code=%d" % code)
    return code


if __name__ == "__main__":
    sys.exit(main())
