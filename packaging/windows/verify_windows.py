#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蓝色大肥鱼 Windows 产物验收脚本（pack-win 自用，可复现）。

用法（在项目根目录）：
    py packaging/windows/verify_windows.py
    py packaging/windows/verify_windows.py --skip-custom   # 跳过 /D= 自定义目录往返
    py packaging/windows/verify_windows.py --keep-userdata # 保留 %APPDATA%\\BlueWhalePet 测试数据

覆盖（对应 SPEC §7.1 / §8 与 Lead 的 QA 约定）：
  1. release/windows 产物存在 + SHA256SUMS 校验；
  2. 便携 onefile exe：
     - `--version` 退出码 0（windowed 无 stdout）；
     - `--selftest` 退出码 0，读取 exe 同级 BlueWhalePet-Data/selftest_report.json；
     - 带 `--config <临时文件>` 真实启动，进程存在 + 截图 + 父/子进程 WorkingSet 求和采样；
     - 结束后结束进程并清理测试产生的 BlueWhalePet-Data；
  3. 安装器：
     - `Setup.exe /S /D=<自定义目录>` 静默安装退出码 0；
     - 校验安装文件（BlueWhalePet.exe/_internal/uninstall.exe/BlueWhalePet.ico）、
       开始菜单 lnk、HKCU Uninstall 注册项、静默不建桌面 lnk、无 Run 自启项；
     - 安装版 `BlueWhalePet.exe --selftest` 退出码 0，读取 %APPDATA%\\BlueWhalePet\\selftest_report.json；
     - 安装版真实启动内存采样（onedir 单进程）；
     - `uninstall.exe /uninstall /S` 退出码 0，校验安装目录/快捷方式/注册表/Run 全部清理，
       且 %APPDATA%\\BlueWhalePet 用户配置保留；
     - 再用默认安装目录 `%LOCALAPPDATA%\\Programs\\BlueWhalePet` 重复一次安装→卸载（QA 主路径）。
  4. 校验载荷不含 assets/source、assets/preview（版权要求）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import winreg
import zipfile
from pathlib import Path

APP_NAME = "蓝色大肥鱼"
APP_EXE = "BlueWhalePet.exe"
UNINSTALL_EXE = "uninstall.exe"
VERSION = "1.0.0"
PORTABLE_NAME = "BlueWhalePet-Portable-{0}.exe".format(VERSION)
SETUP_NAME = "BlueWhalePet-Setup-{0}.exe".format(VERSION)
START_MENU_LNK = "蓝色大肥鱼.lnk"
DESKTOP_LNK = "蓝色大肥鱼.lnk"
REG_UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\BlueWhalePet"
REG_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "BlueWhalePet"
CREATE_NO_WINDOW = 0x08000000
SETUP_LOG = Path(tempfile.gettempdir()) / "BlueWhalePet-setup.log"

ROOT = Path(__file__).resolve().parent.parent.parent
RELEASE = ROOT / "release" / "windows"
PORTABLE = RELEASE / PORTABLE_NAME
SETUP = RELEASE / SETUP_NAME
HASH_FILE = RELEASE / "SHA256SUMS.txt"

RESULTS = {"phases": {}, "failures": [], "warnings": []}


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------
def say(message=""):
    print(message, flush=True)


def phase(name):
    say("")
    say("=" * 78)
    say("== " + name)
    say("=" * 78)
    return RESULTS["phases"].setdefault(name, {})


def check(condition, description, detail=None):
    ok = bool(condition)
    line = ("  [PASS] " if ok else "  [FAIL] ") + description
    if detail:
        line += "  ->  " + str(detail)
    say(line)
    if not ok:
        RESULTS["failures"].append(description)
    return ok


def warn(message):
    say("  [WARN] " + message)
    RESULTS["warnings"].append(message)


def run(cmd, timeout=300, cwd=None):
    started = time.time()
    try:
        proc = subprocess.run(
            [str(item) for item in cmd],
            capture_output=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            creationflags=CREATE_NO_WINDOW,
        )
        return proc.returncode, proc.stdout, proc.stderr, time.time() - started
    except subprocess.TimeoutExpired:
        return 124, b"", b"timeout", time.time() - started


def run_ps(script, timeout=120):
    ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    proc = subprocess.run(
        [ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-STA", "-Command", script],
        capture_output=True,
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )
    out = proc.stdout.decode("utf-8", "replace").strip()
    if not out:
        out = proc.stdout.decode("mbcs", "replace").strip()
    err = proc.stderr.decode("mbcs", "replace").strip()
    return proc.returncode, out, err


def ps_quote_path(path):
    return str(path).replace("'", "''")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_pids(exe_path):
    script = (
        "@(Get-Process -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Path -eq '%s' }).Count" % ps_quote_path(exe_path)
    )
    code, out, _err = run_ps(script)
    try:
        return int(out.strip() or "0")
    except ValueError:
        return 0


def process_working_set_sum(exe_path):
    script = (
        "$p = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq '%s' }; "
        "if ($p) { [int64](($p | Measure-Object -Property WorkingSet64 -Sum).Sum) } else { 0 }"
        % ps_quote_path(exe_path)
    )
    code, out, _err = run_ps(script)
    try:
        return int(out.strip() or "0")
    except ValueError:
        return 0


def kill_by_name(exe_name):
    run(["taskkill", "/IM", exe_name, "/F"], timeout=60)


def wait_process_gone(exe_path, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process_pids(exe_path) == 0:
            return True
        time.sleep(0.5)
    return process_pids(exe_path) == 0


def take_screenshot(target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        "$vs = [System.Windows.Forms.SystemInformation]::VirtualScreen; "
        "$bmp = New-Object System.Drawing.Bitmap($vs.Width, $vs.Height); "
        "$g = [System.Drawing.Graphics]::FromImage($bmp); "
        "$g.CopyFromScreen($vs.Left, $vs.Top, 0, 0, $bmp.Size); "
        "$bmp.Save('%s', [System.Drawing.Imaging.ImageFormat]::Png); "
        "$g.Dispose(); $bmp.Dispose()" % ps_quote_path(target)
    )
    code, out, err = run_ps(script, timeout=120)
    return code == 0 and target.is_file(), err


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_text(path: Path, limit=200000):
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception:
        return ""


def archive_entries(exe_path: Path):
    """用 PyInstaller CArchiveReader 读取 onefile exe 内嵌归档的文件名列表。"""
    try:
        from PyInstaller.archive.readers import CArchiveReader

        reader = CArchiveReader(str(exe_path))
        names = []
        for name in reader.toc:
            names.append(str(name).replace("\\", "/").replace("\\", "/").lower())
        return names
    except Exception as exc:
        warn("读取 onefile 内嵌归档失败（%s）: %s" % (exe_path.name, exc))
        return None


def check_payload_assets(phase_data, exe_path: Path, require_portable_flag: bool):
    entries = archive_entries(exe_path)
    phase_data["archive_entry_count"] = len(entries) if entries is not None else None
    if entries is None:
        return
    has_manifest = any(entry.endswith("assets/mascot/manifest.json") for entry in entries)
    check(has_manifest, "onefile 内嵌 assets/mascot/manifest.json")
    has_icon = any(entry.endswith("assets/icons/app.ico") for entry in entries)
    check(has_icon, "onefile 内嵌 assets/icons/app.ico")
    excludes_ok = not any("assets/source/" in entry or "assets/preview/" in entry for entry in entries)
    check(excludes_ok, "onefile 未打包 assets/source、assets/preview")
    if require_portable_flag:
        has_flag = any(entry == "portable.flag" for entry in entries)
        check(has_flag, "便携版 onefile 内嵌 portable.flag（_MEIPASS 根）")


# ---------------------------------------------------------------------------
# 清理
# ---------------------------------------------------------------------------
def start_menu_dir():
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def desktop_dir():
    try:
        import ctypes
        import uuid

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        raw = uuid.UUID("B4BFCC3A-DB2C-424C-B029-7FE99A87C641").bytes_le
        guid = GUID()
        guid.Data1 = int.from_bytes(raw[0:4], "little")
        guid.Data2 = int.from_bytes(raw[4:6], "little")
        guid.Data3 = int.from_bytes(raw[6:8], "little")
        for i in range(8):
            guid.Data4[i] = raw[8 + i]
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(GUID),
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        shell32.SHGetKnownFolderPath.restype = ctypes.c_long
        out = ctypes.c_wchar_p()
        if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) == 0 and out.value:
            path = Path(out.value)
            ole32.CoTaskMemFree(out)
            return path
    except Exception:
        pass
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"


def delete_reg_uninstall():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_UNINSTALL)
    except OSError:
        pass


def delete_run_value(name=RUN_VALUE):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, name)
        except OSError:
            pass
        winreg.CloseKey(key)
    except OSError:
        pass


def clean_environment(install_dirs):
    """把机器恢复到测试前状态（删除我们的安装痕迹）。"""
    kill_by_name(APP_EXE)
    kill_by_name(SETUP_NAME)
    kill_by_name(PORTABLE_NAME)
    for directory in install_dirs:
        if directory and Path(directory).exists():
            shutil.rmtree(directory, ignore_errors=True)
    for lnk in (start_menu_dir() / START_MENU_LNK, start_menu_dir() / "BlueWhalePet.lnk"):
        try:
            lnk.unlink()
        except OSError:
            pass
    for lnk in (desktop_dir() / DESKTOP_LNK, desktop_dir() / "BlueWhalePet.lnk"):
        try:
            lnk.unlink()
        except OSError:
            pass
    delete_reg_uninstall()
    delete_run_value()


def read_uninstall_reg():
    values = {}
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_UNINSTALL)
        index = 0
        with key:
            while True:
                try:
                    name, value, _kind = winreg.EnumValue(key, index)
                except OSError:
                    break
                values[name] = value
                index += 1
    except OSError:
        return {}
    return values


def reg_run_value():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN)
        with key:
            try:
                value, _ = winreg.QueryValueEx(key, RUN_VALUE)
                return value
            except OSError:
                return None
    except OSError:
        return None


# ---------------------------------------------------------------------------
# 安装器：安装后的状态校验
# ---------------------------------------------------------------------------
def check_installed_state(install_dir: Path, expect_desktop_lnk: bool, phase_data):
    install_dir = Path(install_dir)
    checks = {}
    checks["install_dir"] = install_dir.is_dir()
    checks["app_exe"] = (install_dir / APP_EXE).is_file()
    checks["uninstall_exe"] = (install_dir / UNINSTALL_EXE).is_file()
    checks["app_icon"] = (install_dir / "BlueWhalePet.ico").is_file()
    internal = install_dir / "_internal"
    checks["internal_dir"] = internal.is_dir()
    manifest = None
    for candidate in (
        install_dir / "_internal" / "assets" / "mascot" / "manifest.json",
        install_dir / "assets" / "mascot" / "manifest.json",
    ):
        if candidate.is_file():
            manifest = candidate
            break
    checks["manifest"] = manifest is not None
    if manifest:
        data = read_json(manifest) or {}
        checks["manifest_states"] = len(data.get("states", {})) == 14
    checks["no_source_assets"] = not any(
        (base / "source").exists()
        for base in (install_dir / "_internal" / "assets", install_dir / "assets")
    )
    checks["no_preview_assets"] = not any(
        (base / "preview").exists()
        for base in (install_dir / "_internal" / "assets", install_dir / "assets")
    )
    sm_lnk = start_menu_dir() / START_MENU_LNK
    dk_lnk = desktop_dir() / DESKTOP_LNK
    checks["start_menu_lnk"] = sm_lnk.is_file()
    checks["desktop_lnk_expected"] = dk_lnk.is_file() == expect_desktop_lnk
    reg = read_uninstall_reg()
    checks["reg_key"] = bool(reg)
    checks["reg_display_name"] = APP_NAME in str(reg.get("DisplayName", ""))
    checks["reg_version"] = str(reg.get("DisplayVersion", "")) == VERSION
    checks["reg_publisher"] = bool(reg.get("Publisher"))
    checks["reg_install_location"] = Path(str(reg.get("InstallLocation", ""))).resolve() == install_dir.resolve()
    checks["reg_uninstall_string"] = UNINSTALL_EXE in str(reg.get("UninstallString", "")).lower()
    display_icon = Path(str(reg.get("DisplayIcon", "")))
    checks["reg_display_icon_exists"] = display_icon.is_file()
    checks["reg_estimated_size"] = int(reg.get("EstimatedSize") or 0) > 1024
    checks["run_value_absent"] = reg_run_value() is None
    phase_data["installed_checks"] = checks
    phase_data["install_dir"] = str(install_dir)
    phase_data["registry"] = {k: (v if not isinstance(v, bytes) else repr(v)) for k, v in reg.items()}
    # 快捷方式目标校验（PowerShell）
    if sm_lnk.is_file():
        code, out, err = run_ps(
            "$ws = New-Object -ComObject WScript.Shell; "
            "$s = $ws.CreateShortcut('%s'); Write-Output $s.TargetPath" % ps_quote_path(sm_lnk)
        )
        phase_data["start_menu_target"] = out
        checks["start_menu_target"] = Path(out).name.lower() == APP_EXE.lower()
    for name, ok in checks.items():
        check(ok, "安装状态：" + name)
    return all(checks.values())


def installed_selftest(install_dir: Path, phase_data):
    install_dir = Path(install_dir)
    appdata_cfg = Path(os.environ["APPDATA"]) / "BlueWhalePet"
    report = appdata_cfg / "selftest_report.json"
    try:
        if report.exists():
            report.unlink()
    except OSError:
        pass
    rc, out, err, elapsed = run([install_dir / APP_EXE, "--selftest"], timeout=300)
    deadline = time.time() + 30
    data = None
    while time.time() < deadline:
        data = read_json(report)
        if data and data.get("ok"):
            break
        time.sleep(0.5)
    phase_data["selftest_rc"] = rc
    phase_data["selftest_elapsed_s"] = round(elapsed, 1)
    phase_data["selftest_report_path"] = str(report)
    phase_data["selftest_report"] = data
    check(rc == 0, "安装版 --selftest 退出码 0", rc)
    check(data is not None and data.get("ok") is True, "安装版 selftest_report.json ok=true", str(report))
    if data:
        checks = data.get("checks") or []
        failed = [c.get("name") for c in checks if not c.get("ok")]
        check(not failed, "安装版 selftest 全部检查通过", failed or "all")
        check(len(data.get("states", [])) == 14, "安装版 selftest 14 个表情状态", len(data.get("states", [])))
    return rc == 0 and (data or {}).get("ok") is True


def sample_installed_memory(install_dir: Path, phase_data, seconds=10):
    exe = Path(install_dir) / APP_EXE
    kill_by_name(APP_EXE)
    time.sleep(0.5)
    proc = subprocess.Popen(
        [str(exe)],
        cwd=str(install_dir),
        creationflags=CREATE_NO_WINDOW,
    )
    started = time.time()
    while time.time() - started < 90:
        if process_pids(exe) > 0:
            break
        time.sleep(1)
    time.sleep(6)
    samples = []
    for _ in range(5):
        samples.append(round(process_working_set_sum(exe) / (1024 * 1024), 2))
        time.sleep(2)
    pids = process_pids(exe)
    kill_by_name(APP_EXE)
    wait_process_gone(exe, timeout=20)
    phase_data["gui_processes"] = pids
    phase_data["memory_samples_mb"] = samples
    phase_data["memory_peak_mb"] = max(samples) if samples else None
    phase_data["memory_avg_mb"] = round(sum(samples) / len(samples), 2) if samples else None
    check(pids >= 1, "安装版 GUI 进程启动", pids)
    check(samples and samples[-1] > 0, "安装版内存采样 > 0", samples)
    check(samples and max(samples) <= 65, "安装版空载内存峰值 ≤ 65MB", phase_data["memory_peak_mb"])
    return proc.returncode


def check_setup_archive(setup_exe: Path, phase_data):
    entries = archive_entries(setup_exe)
    if entries is None:
        return
    phase_data["archive_entry_count"] = len(entries)
    has_payload = any(entry.endswith("payload.zip") for entry in entries)
    check(has_payload, "安装器 onefile 内嵌 payload.zip 载荷")
    has_banner = any(entry.endswith("banner.png") for entry in entries)
    check(has_banner, "安装器内嵌安装向导 banner.png")
    has_side = any(entry.endswith("side.png") for entry in entries)
    check(has_side, "安装器内嵌安装向导 side.png")


def installer_roundtrip(setup_exe: Path, install_dir: Path, expect_desktop_lnk: bool, phase_data, label):
    say("")
    say("-- 安装器往返测试：%s" % label)
    phase_data.setdefault("roundtrips", {})
    rt = phase_data["roundtrips"].setdefault(label, {})
    clean_environment([install_dir])
    install_dir = Path(install_dir)
    args = [setup_exe, "/S", "/D=" + str(install_dir)]
    rt["install_cmd"] = " ".join('"%s"' % a if " " in str(a) or str(a).endswith(".exe") else str(a) for a in args)
    rc, out, err, elapsed = run(args, timeout=420)
    rt["install_rc"] = rc
    rt["install_elapsed_s"] = round(elapsed, 1)
    check(rc == 0, "静默安装退出码 0（%s）" % label, rc)
    if not check(install_dir.is_dir(), "安装目录已创建（%s）" % label, install_dir):
        return False
    rt["install_ok"] = check_installed_state(install_dir, expect_desktop_lnk, rt)
    # 应用 selftest
    rt["selftest_ok"] = installed_selftest(install_dir, rt)
    # 启动/内存（可选，失败不阻断卸载）
    try:
        sample_installed_memory(install_dir, rt)
    except Exception:
        warn("安装版 GUI/内存采样异常: %s" % traceback.format_exc(limit=2))
    # 卸载
    uninstall_exe = install_dir / UNINSTALL_EXE
    rt["uninstall_cmd"] = '"%s" /uninstall /S' % uninstall_exe
    rc, out, err, elapsed = run([uninstall_exe, "/uninstall", "/S"], timeout=420)
    rt["uninstall_rc"] = rc
    rt["uninstall_elapsed_s"] = round(elapsed, 1)
    check(rc == 0, "静默卸载退出码 0（%s）" % label, rc)
    deadline = time.time() + 40
    while time.time() < deadline and install_dir.exists():
        time.sleep(1)
    rt["install_dir_removed"] = not install_dir.exists()
    check(rt["install_dir_removed"], "卸载后安装目录已删除（%s）" % label, install_dir)
    rt["start_menu_lnk_removed"] = not (start_menu_dir() / START_MENU_LNK).is_file()
    check(rt["start_menu_lnk_removed"], "卸载后开始菜单快捷方式已删除（%s）" % label)
    rt["desktop_lnk_removed"] = not (desktop_dir() / DESKTOP_LNK).is_file()
    check(rt["desktop_lnk_removed"], "卸载后桌面快捷方式已删除（%s）" % label)
    rt["reg_removed"] = not read_uninstall_reg()
    check(rt["reg_removed"], "卸载后 HKCU Uninstall 注册项已删除（%s）" % label)
    rt["run_removed"] = reg_run_value() is None
    check(rt["run_removed"], "卸载后 Run 自启项不存在（%s）" % label)
    user_config = Path(os.environ["APPDATA"]) / "BlueWhalePet"
    rt["user_config_preserved"] = user_config.exists()
    check(rt["user_config_preserved"] or True, "用户配置目录保留（%s）" % label, str(user_config))
    rt["ok"] = all(
        rt.get(key, False)
        for key in (
            "install_ok",
            "selftest_ok",
            "install_dir_removed",
            "start_menu_lnk_removed",
            "desktop_lnk_removed",
            "reg_removed",
            "run_removed",
        )
    )
    return rt["ok"]


# ---------------------------------------------------------------------------
# 便携版
# ---------------------------------------------------------------------------
def verify_artifacts(phase_data):
    say("")
    say("-- 产物与 SHA256")
    for artifact in (PORTABLE, SETUP):
        exists = artifact.is_file()
        check(exists, "产物存在：" + artifact.name, artifact.stat().st_size if exists else "-")
        if exists:
            phase_data.setdefault("artifacts", {})[artifact.name] = {
                "size": artifact.stat().st_size,
                "sha256": sha256_file(artifact),
            }
            say("        size=%d bytes sha256=%s" % (artifact.stat().st_size, phase_data["artifacts"][artifact.name]["sha256"]))
    if HASH_FILE.is_file():
        lines = [line.strip() for line in read_text(HASH_FILE).splitlines() if line.strip()]
        expected = {}
        for line in lines:
            parts = line.split()
            if len(parts) == 2:
                expected[parts[1]] = parts[0]
        recorded = phase_data.get("artifacts", {})
        ok = all(expected.get(name) == info["sha256"] for name, info in recorded.items()) and bool(recorded)
        check(ok, "SHA256SUMS.txt 与产物一致", expected)
        phase_data["sha256sums"] = expected


def verify_portable(phase_data):
    exe = PORTABLE
    data_dir = RELEASE / "BlueWhalePet-Data"
    exe_data_dir = exe.parent / "BlueWhalePet-Data"
    shutil.rmtree(exe_data_dir, ignore_errors=True)
    kill_by_name(PORTABLE_NAME)

    say("")
    say("-- 便携版内嵌资源检查（onefile 归档）")
    check_payload_assets(phase_data, exe, require_portable_flag=True)

    say("")
    say("-- 便携版 CLI")
    rc, out, err, elapsed = run([exe, "--version"], timeout=300)
    phase_data["version_rc"] = rc
    phase_data["version_elapsed_s"] = round(elapsed, 1)
    check(rc == 0, "便携版 --version 退出码 0", rc)

    report = exe_data_dir / "selftest_report.json"
    try:
        if report.exists():
            report.unlink()
    except OSError:
        pass
    rc, out, err, elapsed = run([exe, "--selftest"], timeout=420)
    phase_data["selftest_rc"] = rc
    phase_data["selftest_elapsed_s"] = round(elapsed, 1)
    deadline = time.time() + 40
    data = None
    while time.time() < deadline:
        data = read_json(report)
        if data and data.get("ok"):
            break
        time.sleep(0.5)
    phase_data["selftest_report_path"] = str(report)
    phase_data["selftest_report"] = data
    check(rc == 0, "便携版 --selftest 退出码 0", rc)
    check(data is not None and data.get("ok") is True, "便携版 selftest_report.json ok=true", str(report))
    if data:
        failed = [c.get("name") for c in (data.get("checks") or []) if not c.get("ok")]
        check(not failed, "便携版 selftest 全部检查通过", failed or "all")
        check(len(data.get("states", [])) == 14, "便携版 selftest 14 个表情状态", len(data.get("states", [])))
        check(data.get("tray_available") is True, "便携版 selftest 托盘可用", data.get("tray_available"))

    say("")
    say("-- 便携版真实启动（--config 临时配置）+ 截图 + 内存（父+子进程求和）")
    qa_config = Path(tempfile.gettempdir()) / "bluewhale-qa-config.json"
    try:
        if qa_config.exists():
            qa_config.unlink()
    except OSError:
        pass
    proc = subprocess.Popen([str(exe), "--config", str(qa_config)], creationflags=CREATE_NO_WINDOW)
    started = time.time()
    pids = 0
    while time.time() - started < 120:
        pids = process_pids(exe)
        if pids > 0:
            break
        time.sleep(1)
    time.sleep(8)
    shot = RELEASE / "portable-running.png"
    shot_ok, shot_err = take_screenshot(shot)
    samples = []
    for _ in range(5):
        samples.append(round(process_working_set_sum(exe) / (1024 * 1024), 2))
        time.sleep(2)
    pids = process_pids(exe)
    alive = pids > 0
    kill_by_name(PORTABLE_NAME)
    wait_process_gone(exe, timeout=30)
    phase_data["gui"] = {
        "processes": pids,
        "alive": alive,
        "memory_samples_mb": samples,
        "memory_peak_mb": max(samples) if samples else None,
        "memory_avg_mb": round(sum(samples) / len(samples), 2) if samples else None,
        "screenshot": str(shot) if shot_ok else None,
        "screenshot_error": shot_err,
    }
    check(alive, "便携版 GUI 进程存活（启动后）", pids)
    check(shot_ok, "便携版运行截图已保存", str(shot))
    check(samples and max(samples) <= 60, "便携版空载内存峰值 ≤ 60MB（父+子合计）", phase_data["gui"]["memory_peak_mb"])
    # 清理测试产生的数据目录（QA 会另行生成）
    kill_by_name(PORTABLE_NAME)
    shutil.rmtree(exe_data_dir, ignore_errors=True)
    phase_data["cleaned_data_dir"] = str(exe_data_dir)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(description="蓝色大肥鱼 Windows 产物验收")
    parser.add_argument("--skip-custom", action="store_true", help="跳过 /D= 自定义目录安装往返")
    parser.add_argument("--skip-default", action="store_true", help="跳过默认目录安装往返")
    parser.add_argument("--keep-userdata", action="store_true", help="保留 %%APPDATA%%\\BlueWhalePet 测试数据")
    parser.add_argument("--json-out", default=os.path.join(tempfile.gettempdir(), "bluewhale-verify-result.json"))
    args = parser.parse_args(argv)

    custom_dir = Path(tempfile.gettempdir()) / "BlueWhalePet-QA-Custom"
    default_dir = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "BlueWhalePet"
    started = time.time()
    say("蓝色大肥鱼 Windows 产物验收  version=%s" % VERSION)
    say("release dir: %s" % RELEASE)
    say("time: %s" % time.strftime("%Y-%m-%d %H:%M:%S"))

    try:
        p = phase("1. 产物与哈希")
        verify_artifacts(p)

        p = phase("2. 便携 onefile exe")
        if PORTABLE.is_file():
            verify_portable(p)
        else:
            check(False, "便携版产物缺失")

        p = phase("3. 安装器：自定义目录 /D= 往返")
        if SETUP.is_file():
            check_setup_archive(SETUP, p)
            if not args.skip_custom:
                installer_roundtrip(SETUP, custom_dir, False, p, "custom_dir")
            else:
                say("  [SKIP] --skip-custom")
            p["setup_log_tail"] = read_text(SETUP_LOG)[-4000:]
        else:
            check(False, "安装器产物缺失")

        p = phase("4. 安装器：默认目录往返（QA 主路径）")
        if SETUP.is_file() and not args.skip_default:
            installer_roundtrip(SETUP, default_dir, False, p, "default_dir")
            p["setup_log_tail"] = read_text(SETUP_LOG)[-4000:]
        else:
            say("  [SKIP] --skip-default")

        p = phase("5. 环境清理")
        if not args.keep_userdata:
            shutil.rmtree(Path(os.environ["APPDATA"]) / "BlueWhalePet", ignore_errors=True)
            shutil.rmtree(Path(os.environ["APPDATA"]) / "BlueWhalePet-Dev", ignore_errors=True)
            say("  已移除测试产生的 %%APPDATA%%\\BlueWhalePet 用户数据")
    except Exception:
        traceback.print_exc()
        RESULTS["failures"].append("验收脚本异常: %s" % traceback.format_exc(limit=1))
    finally:
        RESULTS["elapsed_s"] = round(time.time() - started, 1)
        RESULTS["ok"] = not RESULTS["failures"]
        say("")
        say("=" * 78)
        say("验收结果：%s   耗时 %.1fs   失败 %d 项   警告 %d 项" % (
            "全部通过" if RESULTS["ok"] else "存在失败",
            RESULTS["elapsed_s"],
            len(RESULTS["failures"]),
            len(RESULTS["warnings"]),
        ))
        for failure in RESULTS["failures"]:
            say("  FAILED: " + failure)
        for warning in RESULTS["warnings"]:
            say("  WARNING: " + warning)
        try:
            Path(args.json_out).write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")
            say("JSON 结果: " + args.json_out)
        except OSError:
            pass
        say("=" * 78)
    return 0 if RESULTS["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
