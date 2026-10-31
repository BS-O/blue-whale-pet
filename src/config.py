"""配置契约实现（SPEC §5）。

- 缺省值见 ``DEFAULT_CONFIG``
- ``load_config`` 深合并默认值 + 校验容错，损坏时备份并回退默认
- ``save_config`` 原子写（临时文件 + os.replace）
- ``load_or_create_config``：文件不存在时按默认配置落盘
"""
from __future__ import annotations

import copy
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

import constants as C
import prompts

logger = logging.getLogger("bluewhale.config")

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "api": {
        "provider": C.DEFAULT_PROVIDER,
        "key": "",
        "keys": {"deepseek": "", "glm": ""},
        "base_url": C.DEFAULT_BASE_URL,
        "model": C.DEFAULT_MODEL,
        "max_tokens": 120,
        "temperature": 1.3,
        "timeout": 30,
    },
    "pet": {
        "size": C.DEFAULT_SIZE,
        "x": None,
        "y": None,
        "always_on_top": True,
        "opacity": 1.0,
        "click_through": False,
    },
    "speech": {
        "persona": prompts.PERSONA_PLACEHOLDER,
        "max_chars": C.DEFAULT_MAX_CHARS,
        "typewriter": True,
        "bubble_seconds": C.DEFAULT_BUBBLE_SECONDS,
    },
    "behavior": {
        "idle_animation": True,
        "auto_sleep_seconds": C.DEFAULT_AUTO_SLEEP_SECONDS,
        "greet_on_start": True,
        "wheel_resize": True,
        "click_actions": True,
    },
    "system": {
        "autostart": False,
        "tray": True,
        "language": "zh",
        "first_run": True,
    },
}



def effective_api(cfg: dict[str, Any]) -> dict[str, Any]:
    """解析当前生效的 API 平台参数（Key 按平台取用，兼容旧 api.key 字段）。"""
    api = (cfg.get("api") or {}) if isinstance(cfg, dict) else {}
    provider = str(api.get("provider") or C.DEFAULT_PROVIDER).lower()
    if provider not in C.PROVIDERS:
        provider = C.DEFAULT_PROVIDER
    preset = C.PROVIDERS[provider]
    keys = api.get("keys") if isinstance(api.get("keys"), dict) else {}
    key = str(keys.get(provider) or api.get("key") or "").strip()
    return {
        "provider": provider,
        "label": preset["label"],
        "key": key,
        "base_url": str(api.get("base_url") or preset["base_url"]).strip().rstrip("/"),
        "model": str(api.get("model") or preset["default_model"]).strip(),
    }


def default_config() -> dict[str, Any]:
    """返回缺省配置的深拷贝。"""
    return copy.deepcopy(DEFAULT_CONFIG)


def deep_merge(base: Any, override: Any) -> Any:
    """深合并：dict 递归合并，其它类型 override 优先（None 不覆盖 dict）。"""
    if isinstance(base, dict) and isinstance(override, dict):
        out = copy.deepcopy(base)
        for key, value in override.items():
            if key in out:
                if isinstance(out[key], dict) and not isinstance(value, dict):
                    continue
                out[key] = deep_merge(out[key], value)
            # 未知键丢弃（保持配置文件干净、向前兼容）
        return out
    if override is None and isinstance(base, dict):
        return copy.deepcopy(base)
    return copy.deepcopy(override)


# ---------------------------------------------------------------------------
# 校验工具
# ---------------------------------------------------------------------------

def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("1", "true", "yes", "on", "是", "开"):
            return True
        if v in ("0", "false", "no", "off", "否", "关"):
            return False
    return default


def _as_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        if isinstance(value, bool):
            return int(value)
        out = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, out))


def _as_float(value: Any, default: float, lo: float, hi: float) -> float:
    try:
        if isinstance(value, bool):
            return float(int(value))
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out:  # NaN
        return default
    return max(lo, min(hi, out))


def _as_str(value: Any, default: str, max_len: int = 4096) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        value = str(value)
    return value.strip()[:max_len]


def _as_opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def normalize_config(raw: Any) -> tuple[dict[str, Any], list[str]]:
    """把任意输入规范成合法配置；返回 (cfg, warnings)。"""
    warnings: list[str] = []
    if not isinstance(raw, dict):
        warnings.append("配置根节点不是对象，已使用默认值")
        raw = {}
    cfg = deep_merge(DEFAULT_CONFIG, raw)

    api = cfg.setdefault("api", {})
    if not isinstance(api, dict):
        api = cfg["api"] = {}
    key = _as_str(api.get("key"), "")
    if "\n" in key or "\r" in key:
        key = "".join(key.split())
    api["key"] = key
    # API 平台与分平台 Key：未知平台回退 deepseek；keys 只保留已知平台
    provider = _as_str(api.get("provider"), C.DEFAULT_PROVIDER, 32).lower()
    if provider not in C.PROVIDERS:
        warnings.append(f"未知 API 平台 {provider!r}，已回退 {C.DEFAULT_PROVIDER}")
        provider = C.DEFAULT_PROVIDER
    api["provider"] = provider
    raw_keys = api.get("keys") if isinstance(api.get("keys"), dict) else {}
    keys = {pid: _as_str(raw_keys.get(pid), "", 256) for pid in C.PROVIDERS}
    # 旧配置迁移：只有 api.key 时视为 DeepSeek 的 Key
    if not any(keys.values()) and key:
        keys[C.DEFAULT_PROVIDER] = key
    api["keys"] = keys
    base_url = _as_str(api.get("base_url"), C.DEFAULT_BASE_URL, 512).rstrip("/")
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        warnings.append(f"base_url 非法，已用默认值: {base_url!r}")
        base_url = C.DEFAULT_BASE_URL
    api["base_url"] = base_url
    model = _as_str(api.get("model"), C.DEFAULT_MODEL, 128)
    api["model"] = model or C.DEFAULT_MODEL
    api["max_tokens"] = _as_int(api.get("max_tokens"), 120, 16, 2048)
    api["temperature"] = _as_float(api.get("temperature"), 1.3, 0.0, 2.0)
    api["timeout"] = _as_int(api.get("timeout"), 30, 5, 120)

    pet = cfg.setdefault("pet", {})
    if not isinstance(pet, dict):
        pet = cfg["pet"] = {}
    size = _as_int(pet.get("size"), C.DEFAULT_SIZE, C.MIN_SIZE, C.MAX_SIZE)
    if size != pet.get("size"):
        if pet.get("size") is not None:
            warnings.append(f"pet.size 越界，已夹到 {size}")
    pet["size"] = size
    pet["x"] = _as_opt_int(pet.get("x"))
    pet["y"] = _as_opt_int(pet.get("y"))
    pet["always_on_top"] = _as_bool(pet.get("always_on_top"), True)
    pet["opacity"] = round(_as_float(pet.get("opacity"), 1.0, 0.3, 1.0), 3)
    pet["click_through"] = _as_bool(pet.get("click_through"), False)

    speech = cfg.setdefault("speech", {})
    if not isinstance(speech, dict):
        speech = cfg["speech"] = {}
    speech["persona"] = _as_str(speech.get("persona"), prompts.PERSONA_PLACEHOLDER)
    speech["max_chars"] = _as_int(speech.get("max_chars"), C.DEFAULT_MAX_CHARS, 10, 200)
    speech["typewriter"] = _as_bool(speech.get("typewriter"), True)
    speech["bubble_seconds"] = _as_int(speech.get("bubble_seconds"), C.DEFAULT_BUBBLE_SECONDS, 1, 60)

    behavior = cfg.setdefault("behavior", {})
    if not isinstance(behavior, dict):
        behavior = cfg["behavior"] = {}
    behavior["idle_animation"] = _as_bool(behavior.get("idle_animation"), True)
    behavior["auto_sleep_seconds"] = _as_int(behavior.get("auto_sleep_seconds"), C.DEFAULT_AUTO_SLEEP_SECONDS, 0, 7200)
    behavior["greet_on_start"] = _as_bool(behavior.get("greet_on_start"), True)
    behavior["wheel_resize"] = _as_bool(behavior.get("wheel_resize"), True)
    behavior["click_actions"] = _as_bool(behavior.get("click_actions"), True)

    system = cfg.setdefault("system", {})
    if not isinstance(system, dict):
        system = cfg["system"] = {}
    system["autostart"] = _as_bool(system.get("autostart"), False)
    system["tray"] = _as_bool(system.get("tray"), True)
    system["language"] = _as_str(system.get("language"), "zh", 16) or "zh"
    system["first_run"] = _as_bool(system.get("first_run"), True)
    cfg["version"] = _as_int(cfg.get("version"), 1, 1, 999)
    return cfg, warnings


# ---------------------------------------------------------------------------
# 读取 / 写入
# ---------------------------------------------------------------------------

def backup_corrupt_config(path: Path, reason: str = "") -> Path | None:
    """把损坏配置另存为 ``config.json.bad-<时间戳>``，返回备份路径。"""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bad-{stamp}")
    try:
        if backup.exists():
            backup = path.with_name(f"{path.name}.bad-{stamp}-{os.getpid()}")
        shutil.copyfile(path, backup)
        logger.warning("配置文件损坏（%s），已备份到 %s", reason, backup)
        return backup
    except OSError:
        logger.exception("备份损坏配置失败: %s", path)
        return None


def load_config(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """读取配置；返回 (cfg, info)。

    info: path / existed / created / recovered / backup / warnings
    """
    path = Path(path)
    info: dict[str, Any] = {
        "path": str(path),
        "existed": False,
        "created": False,
        "recovered": False,
        "backup": None,
        "warnings": [],
    }
    if not path.exists():
        cfg, warnings = normalize_config(default_config())
        info["created"] = True
        info["warnings"] = warnings
        return cfg, info
    info["existed"] = True
    try:
        text = path.read_text(encoding="utf-8")
        raw = json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        info["recovered"] = True
        info["backup"] = str(backup_corrupt_config(path, str(exc)) or "")
        cfg, warnings = normalize_config(default_config())
        warnings.append(f"配置损坏已恢复默认: {exc}")
        info["warnings"] = warnings
        return cfg, info
    cfg, warnings = normalize_config(raw)
    info["warnings"] = warnings
    return cfg, info


def save_config(path: Path, cfg: dict[str, Any]) -> bool:
    """原子写配置文件；返回是否成功。绝不抛异常。"""
    path = Path(path)
    data, _ = normalize_config(cfg)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
            return True
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
    except OSError:
        logger.exception("写入配置失败: %s", path)
        return False


def load_or_create_config(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """读取配置；不存在则按默认值创建并落盘。"""
    cfg, info = load_config(path)
    if info.get("created"):
        ok = save_config(path, cfg)
        info["created"] = ok
        if not ok:
            info["warnings"].append("无法写入新配置文件，本次仅在内存中使用默认配置")
    return cfg, info


def config_to_json(cfg: dict[str, Any]) -> str:
    data, _ = normalize_config(cfg)
    return json.dumps(data, ensure_ascii=False, indent=2)
