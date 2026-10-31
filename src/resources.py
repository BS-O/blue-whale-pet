"""资源路径 / 数据目录解析（SPEC §3、§5）。

- 开发模式：项目根 ``assets/``
- 冻结模式：``sys._MEIPASS/assets``
- 便携模式：``sys._MEIPASS/portable.flag`` 存在 → exe 同级 ``BlueWhalePet-Data/``（不可写回退 %APPDATA%）
- 安装版 Windows：``%APPDATA%\\BlueWhalePet``
- Linux：``$XDG_CONFIG_HOME/blue-whale-pet``
- 开发态数据目录独立（``BlueWhalePet-Dev``），避免污染安装版
- 可用环境变量 ``BLUEWHALE_DATA_DIR`` 覆盖（QA/测试用）
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import constants as C

_ENV_DATA_DIR = "BLUEWHALE_DATA_DIR"
_data_dir_cache: Path | None = None


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def exe_path() -> Path:
    """当前可执行文件路径（冻结态为 exe，开发态为 python 解释器）。"""
    return Path(sys.executable).resolve()


def exe_dir() -> Path:
    if is_frozen():
        return exe_path().parent
    return Path(__file__).resolve().parent.parent


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def src_dir() -> Path:
    return Path(__file__).resolve().parent


def main_script_path() -> Path:
    return src_dir() / "main.py"


def asset_root() -> Path:
    """资产根目录。

    优先级：环境变量 ``BLUE_WHALE_PET_ASSETS``（Linux 安装版由启动器设置）
    → 冻结态 ``_MEIPASS/assets`` → 开发/安装态 ``<src 上级>/assets``。
    """
    env = os.environ.get("BLUE_WHALE_PET_ASSETS")
    if env:
        candidate = Path(env).expanduser()
        if candidate.is_dir():
            return candidate
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass) / "assets"
        return exe_dir() / "assets"
    return project_root() / "assets"


def manifest_path() -> Path:
    return asset_root() / "mascot" / "manifest.json"


def mascot_dir() -> Path:
    return asset_root() / "mascot" / "master"


def icon_path(name: str) -> Path:
    return asset_root() / "icons" / name


def app_icon_path() -> Path:
    """窗口图标（优先 app.ico）。"""
    p = icon_path("app.ico")
    return p if p.exists() else icon_path("tray.ico")


def tray_icon_path() -> Path:
    p = icon_path("tray.ico")
    if p.exists():
        return p
    return app_icon_path()


def about_image_path() -> Path:
    p = icon_path("app.png")
    return p if p.exists() else icon_path("tray.ico")


def is_portable() -> bool:
    """便携模式：冻结 + _MEIPASS/portable.flag。"""
    if not is_frozen():
        return False
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return (Path(meipass) / "portable.flag").exists()
    return (exe_dir() / "portable.flag").exists()


def _appdata_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / C.APP_ID
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / C.APP_PACKAGE


def _dev_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / (C.APP_ID + "-Dev")
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / (C.APP_PACKAGE + "-dev")


def _dir_writable(path: Path) -> bool:
    """判断目录（或最近的已存在父目录）是否可写；不存在也会尝试创建。"""
    try:
        if path.exists() and not path.is_dir():
            return False
        path.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".wtest_", dir=str(path))
        os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return True
    except OSError:
        return False


def _is_installed_linux() -> bool:
    """判定“Linux 安装态”（非 frozen 但代码位于 /usr/lib/blue-whale-pet）。

    安装版由启动器 `python3 /usr/lib/blue-whale-pet/main.py` 运行，不是 frozen，
    但数据目录必须用 ~/.config/blue-whale-pet（SPEC §5 / QA 契约），不能用开发目录。
    判定优先级：环境变量 BLUE_WHALE_PET_INSTALLED=1 → 安装树没有 SPEC.md/.git。
    """
    if is_frozen() or sys.platform != "linux":
        return False
    if os.environ.get("BLUE_WHALE_PET_INSTALLED") == "1":
        return True
    try:
        root = project_root()
        return not (root / "SPEC.md").exists() and not (root / ".git").exists()
    except OSError:
        return False


def data_dir() -> Path:
    """数据目录（配置/日志/自检报告）。结果缓存。"""
    global _data_dir_cache
    if _data_dir_cache is not None:
        return _data_dir_cache

    env = os.environ.get(_ENV_DATA_DIR)
    if env:
        p = Path(env).expanduser()
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        _data_dir_cache = p
        return p

    if is_portable():
        p = exe_dir() / "BlueWhalePet-Data"
        if _dir_writable(p):
            _data_dir_cache = p
            return p
        # 便携目录不可写 → 回退安装版目录
    if is_frozen() or _is_installed_linux():
        _data_dir_cache = _appdata_dir()
    else:
        _data_dir_cache = _dev_dir()
    return _data_dir_cache


def set_data_dir_override(path: str | os.PathLike[str] | None) -> None:
    """测试用：显式覆盖数据目录（None 清除缓存重新解析）。"""
    global _data_dir_cache
    if path is None:
        os.environ.pop(_ENV_DATA_DIR, None)
        _data_dir_cache = None
        return
    p = Path(path)
    os.environ[_ENV_DATA_DIR] = str(p)
    _data_dir_cache = p


def logs_dir() -> Path:
    return data_dir() / "logs"


def default_config_path() -> Path:
    return data_dir() / "config.json"


def selftest_report_path() -> Path:
    return data_dir() / "selftest_report.json"


def dump_config_path() -> Path:
    return data_dir() / "dump-config.json"


def ensure_dirs() -> None:
    for d in (data_dir(), logs_dir()):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def _writable_target(path: Path) -> bool:
    """目标配置文件是否可写（父目录可写；已有文件时文件本身可写）。"""
    parent = path.parent
    if not _dir_writable(parent):
        return False
    if path.exists():
        try:
            with open(path, "a", encoding="utf-8"):
                pass
            return True
        except OSError:
            return False
    return True


def resolve_config_path(cli_path: str | None) -> tuple[Path, str]:
    """解析配置文件路径。

    返回 ``(path, note)``；当 ``--config`` 指向不可写位置时降级到默认路径，
    note 为降级说明（供日志）。不存在的文件是合法的（后续按默认配置落盘）。
    """
    if not cli_path:
        return default_config_path(), ""
    raw = Path(cli_path).expanduser()
    try:
        target = raw if raw.is_absolute() else (Path.cwd() / raw)
        target = target.resolve()
    except OSError:
        target = Path(os.path.abspath(str(raw)))
    try:
        if target.exists() and target.is_dir():
            fallback = default_config_path()
            return fallback, f"--config 指向目录，已降级: {target} -> {fallback}"
        if _writable_target(target):
            return target, ""
    except OSError:
        pass
    fallback = default_config_path()
    return fallback, f"--config 路径不可写，已降级: {target} -> {fallback}"


def launch_command() -> list[str]:
    """开机自启使用的命令行（冻结态=exe；开发态=pythonw + main.py）。"""
    if is_frozen():
        return [str(exe_path())]
    exe = sys.executable
    if sys.platform == "win32":
        cand = Path(exe).with_name("pythonw.exe")
        if cand.exists():
            exe = str(cand)
    return [exe, str(main_script_path())]


def quote_command(cmd: list[str]) -> str:
    """把命令列表转成 Windows 注册表/桌面文件的带引号字符串。"""
    parts = []
    for arg in cmd:
        if not arg:
            continue
        if any(ch.isspace() for ch in arg) or '"' in arg:
            parts.append('"' + arg.replace('"', '\\"') + '"')
        else:
            parts.append('"' + arg + '"')
    return " ".join(parts)


def asset_report() -> dict:
    """资产存在性摘要（selftest / dump-config 用）。"""
    root = asset_root()
    return {
        "asset_root": str(root),
        "manifest": str(manifest_path()),
        "manifest_exists": manifest_path().is_file(),
        "app_icon_exists": app_icon_path().is_file(),
        "tray_icon_exists": tray_icon_path().is_file(),
        "icons_dir_exists": (root / "icons").is_dir(),
    }


def copy_file(src: Path, dst: Path) -> bool:
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        return True
    except OSError:
        return False
