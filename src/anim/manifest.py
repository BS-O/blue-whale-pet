"""资产清单 ``assets/mascot/manifest.json`` 解析与校验（SPEC §4.1）。

代码完全按 manifest 动态加载：禁止硬编码帧数 / 文件名 / 表情名。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import constants as C

logger = logging.getLogger("bluewhale.anim.manifest")


class ManifestError(Exception):
    pass


def _parse_color(value: Any) -> tuple[int, int, int]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return tuple(max(0, min(255, int(v))) for v in value[:3])  # type: ignore[return-value]
        except (TypeError, ValueError):
            pass
    if isinstance(value, str) and value.startswith("#") and len(value) >= 7:
        try:
            return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
        except ValueError:
            pass
    return C.DEFAULT_KEY_RGB


def color_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


class Manifest:
    """解析后的资产清单。"""

    def __init__(self, data: dict[str, Any], path: Path | None = None) -> None:
        self.path = path
        self.raw = data
        canvas = data.get("canvas") or {}
        try:
            self.canvas_w = int(canvas.get("w") or 512)
            self.canvas_h = int(canvas.get("h") or 512)
        except (TypeError, ValueError):
            raise ManifestError("canvas 尺寸非法") from None
        if self.canvas_w <= 0 or self.canvas_h <= 0:
            raise ManifestError("canvas 尺寸必须为正数")
        try:
            self.anchor_x = int(canvas.get("anchor_x", self.canvas_w // 2))
            self.anchor_y = int(canvas.get("anchor_y", self.canvas_h))
        except (TypeError, ValueError):
            self.anchor_x, self.anchor_y = self.canvas_w // 2, self.canvas_h
        self.key_rgb = _parse_color(data.get("key_color") or C.DEFAULT_KEY_COLOR)
        self.key_color = color_to_hex(self.key_rgb)
        try:
            self.version = int(data.get("version") or 1)
        except (TypeError, ValueError):
            self.version = 1

        states = data.get("states")
        if not isinstance(states, dict) or not states:
            raise ManifestError("manifest 缺少 states")
        self.states: dict[str, dict[str, Any]] = {}
        for name, info in states.items():
            if not isinstance(name, str) or not name:
                continue
            if not isinstance(info, dict):
                logger.warning("忽略非法表情定义: %r", name)
                continue
            frames = [str(f) for f in (info.get("frames") or []) if str(f).strip()]
            if not frames:
                logger.warning("表情 %s 没有帧，已忽略", name)
                continue
            raw_durations = info.get("durations") or []
            durations: list[int] = []
            for i, frame in enumerate(frames):
                value = raw_durations[i] if i < len(raw_durations) else 300
                try:
                    duration = int(float(value))
                except (TypeError, ValueError):
                    duration = 300
                durations.append(max(16, min(10000, duration)))
            self.states[name] = {
                "frames": frames,
                "durations": durations,
                "loop": bool(info.get("loop", False)),
            }
        if not self.states:
            raise ManifestError("manifest 没有可用表情")

        default = data.get("default_state")
        if not isinstance(default, str) or default not in self.states:
            default = "idle" if "idle" in self.states else next(iter(self.states))
        self.default_state: str = default

    # -- 基本查询 ---------------------------------------------------------
    def state_names(self) -> list[str]:
        return list(self.states.keys())

    def has_state(self, state: str) -> bool:
        return state in self.states

    def frames(self, state: str) -> list[str]:
        info = self.states.get(state) or self.states[self.default_state]
        return list(info["frames"])

    def durations(self, state: str) -> list[int]:
        info = self.states.get(state) or self.states[self.default_state]
        return list(info["durations"])

    def loop(self, state: str) -> bool:
        info = self.states.get(state) or self.states[self.default_state]
        return bool(info["loop"])

    def frame_count(self, state: str | None = None) -> int:
        if state is None:
            return sum(len(info["frames"]) for info in self.states.values())
        return len(self.states[state]["frames"]) if state in self.states else 0

    @property
    def frame_total(self) -> int:
        return sum(len(info["frames"]) for info in self.states.values())

    @property
    def aspect(self) -> float:
        return self.canvas_h / float(self.canvas_w)

    @property
    def required_missing(self) -> list[str]:
        return [state for state in C.REQUIRED_STATES if state not in self.states]

    # -- 帧文件路径 -------------------------------------------------------
    def master_dir(self) -> Path:
        if self.path is not None:
            return Path(self.path).parent / "master"
        import resources  # 延迟导入，避免循环

        return resources.mascot_dir()

    def frame_path(self, frame_name: str) -> Path:
        name = frame_name.strip()
        if not name.lower().endswith(".png"):
            name += ".png"
        return self.master_dir() / name

    # -- 加载 -------------------------------------------------------------
    @classmethod
    def load(cls, path: Path) -> "Manifest":
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ManifestError(f"无法读取 manifest: {path} ({exc})") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"manifest 不是合法 JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ManifestError("manifest 根节点必须是对象")
        return cls(data, path)

    def missing_frames(self) -> list[str]:
        """返回不存在的帧文件（按 manifest 顺序）。"""
        missing: list[str] = []
        for state in self.states:
            for frame in self.states[state]["frames"]:
                if not self.frame_path(frame).is_file():
                    missing.append(f"{state}:{frame}")
        return missing

    def summary(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "canvas": [self.canvas_w, self.canvas_h],
            "anchor": [self.anchor_x, self.anchor_y],
            "key_color": self.key_color,
            "default_state": self.default_state,
            "states": self.state_names(),
            "state_count": len(self.states),
            "frame_count": self.frame_total,
            "required_missing": self.required_missing,
        }
