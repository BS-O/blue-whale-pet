"""表情帧加载与缓存（低内存关键模块）。

- 仅缓存当前/最近 ``max_states`` 个表情的**显示尺寸**帧（不保留 512 原图）
- Windows：RGBA 合成到色键背景 → RGB PhotoImage（配合 -transparentcolor）
- Linux：同样合成显示图；额外生成 1bit mask 供 ctypes XShape 剪裁
- 尺寸变化时整体清空缓存；``clear()`` 立即释放 PhotoImage
"""
from __future__ import annotations

import logging
import sys
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from PIL import Image, ImageTk

import constants as C
from anim.manifest import Manifest

logger = logging.getLogger("bluewhale.anim.frames")

CacheEntry = tuple[Any, bytes | None]  # (ImageTk.PhotoImage, mask_bytes|None)


def default_sprite_mode() -> str:
    """chroma: Windows 色键；shape: Linux XShape；alpha: 兜底。"""
    if sys.platform == "win32":
        return "chroma"
    return "shape"


def alpha_to_mask_bytes(alpha: Image.Image, threshold: int = 40) -> bytes:
    """RGBA 的 alpha 通道 → X11 位图格式（每行按字节对齐，LSB first）。"""
    gray = alpha.convert("L")
    w, h = gray.size
    data = gray.tobytes()
    row_bytes = (w + 7) // 8
    out = bytearray(row_bytes * h)
    idx = 0
    for y in range(h):
        base = y * row_bytes
        for x in range(w):
            if data[idx] >= threshold:
                out[base + (x >> 3)] |= 1 << (x & 7)
            idx += 1
    return bytes(out)


class SpriteCache:
    """按 state 懒加载 + 显示尺寸缩放缓存。"""

    def __init__(
        self,
        manifest: Manifest,
        mode: str | None = None,
        key_rgb: tuple[int, int, int] | None = None,
        max_states: int = 3,
        logger_: logging.Logger | None = None,
    ) -> None:
        self.manifest = manifest
        self.mode = mode or default_sprite_mode()
        self.key_rgb = key_rgb or manifest.key_rgb or C.DEFAULT_KEY_RGB
        self.max_states = max(1, int(max_states))
        self.log = logger_ or logger
        self.render_size: tuple[int, int] | None = None
        self._cache: "OrderedDict[str, dict[str, CacheEntry]]" = OrderedDict()
        self._load_errors: list[str] = []

    # ------------------------------------------------------------------
    def set_render_size(self, width: int, height: int) -> bool:
        """设置显示尺寸；变化时清空缓存并返回 True。"""
        width = max(8, int(width))
        height = max(8, int(height))
        if self.render_size == (width, height):
            return False
        self.render_size = (width, height)
        self.clear()
        return True

    def window_size_for(self, logical_size: int) -> tuple[int, int]:
        """由逻辑尺寸（长边像素）按 canvas 宽高比算出窗口宽高。"""
        logical_size = max(C.MIN_SIZE, min(C.MAX_SIZE, int(logical_size)))
        aspect = self.manifest.aspect
        if aspect == 1.0:
            return logical_size, logical_size
        return logical_size, max(8, int(round(logical_size * aspect)))

    # ------------------------------------------------------------------
    def get(self, state: str, frame_name: str) -> CacheEntry | None:
        if self.render_size is None:
            raise RuntimeError("SpriteCache 未设置 render_size")
        state_frames = self._cache.get(state)
        if state_frames is not None and frame_name in state_frames:
            self._cache.move_to_end(state)
            return state_frames[frame_name]
        if not self.manifest.has_state(state):
            state = self.manifest.default_state
            state_frames = self._cache.get(state)
            if state_frames is not None and frame_name in state_frames:
                self._cache.move_to_end(state)
                return state_frames[frame_name]
        entry = self._load_frame(state, frame_name)
        if entry is None:
            return self._fallback_entry(state)
        state_frames = self._cache.setdefault(state, {})
        state_frames[frame_name] = entry
        self._cache.move_to_end(state)
        self._evict()
        return entry

    def prepare(self, state: str) -> bool:
        """预加载某表情全部帧（切表情时调用，避免逐帧解码卡顿）。"""
        if not self.manifest.has_state(state):
            return False
        ok = True
        for frame_name in self.manifest.frames(state):
            if self.get(state, frame_name) is None:
                ok = False
        return ok

    def clear(self) -> None:
        self._cache.clear()

    @property
    def loaded_states(self) -> list[str]:
        return list(self._cache.keys())

    @property
    def load_errors(self) -> list[str]:
        return list(self._load_errors)

    # ------------------------------------------------------------------
    def _evict(self) -> None:
        while len(self._cache) > self.max_states:
            old_state, _ = self._cache.popitem(last=False)
            self.log.debug("缓存淘汰表情: %s", old_state)

    def _fallback_entry(self, state: str) -> CacheEntry | None:
        default = self.manifest.default_state
        if state != default:
            return self.get(default, self.manifest.frames(default)[0])
        return None

    def _render_image(self, frame_name: str) -> tuple[Any, bytes | None] | None:
        """纯 Pillow 渲染（线程安全，不触碰 Tk），返回 (RGB 合成图, mask)。"""
        path = self.manifest.frame_path(frame_name)
        try:
            with Image.open(path) as raw:
                raw.load()
                image = raw.convert("RGBA")
        except (OSError, ValueError) as exc:
            message = f"{path}: {exc}"
            if len(self._load_errors) < 32:
                self._load_errors.append(message)
            self.log.warning("表情帧加载失败 %s", message)
            return None
        w, h = self.render_size or (self.manifest.canvas_w, self.manifest.canvas_h)
        if image.size != (w, h):
            image = image.resize((w, h), Image.LANCZOS)
        mask: bytes | None = None
        if self.mode == "shape":
            mask = alpha_to_mask_bytes(image.getchannel("A"))
        rgb = self._chroma_composite(image)
        return rgb, mask

    def _load_frame(self, state: str, frame_name: str) -> CacheEntry | None:
        rendered = self._render_image(frame_name)
        if rendered is None:
            return None
        rgb, mask = rendered
        photo = ImageTk.PhotoImage(rgb, master=None)
        return (photo, mask)

    def _chroma_composite(self, image: Image.Image) -> Image.Image:
        key = self.key_rgb
        base = Image.new("RGB", image.size, key)
        base.paste(image, (0, 0), image)
        # 把近乎全透明的像素精确压回色键，消除缩放产生的暗色薄雾
        transparent = image.getchannel("A").point(lambda value: 255 if value < 6 else 0)
        base.paste(Image.new("RGB", image.size, key), (0, 0), transparent)
        return base

    # ------------------------------------------------------------------
    def verify_all(self, populate: bool = False, workers: int = 8) -> dict[str, Any]:
        """selftest 用：为 manifest 中每个表情的每一帧创建 PhotoImage。

        ``populate=True`` 时把帧留在缓存里（配合临时提高 max_states），
        让后续表情切换/交互检查走内存缓存，避免在慢磁盘上反复解码。
        Pillow 解码在线程池并行完成（不触碰 Tk），PhotoImage 在主线程创建。
        """
        if self.render_size is None:
            self.set_render_size(self.manifest.canvas_w // 3, self.manifest.canvas_h // 3)
        tasks: list[tuple[str, str]] = []
        for state in self.manifest.state_names():
            for frame_name in self.manifest.frames(state):
                tasks.append((state, frame_name))
        created = 0
        failed: list[str] = []
        try:
            with ThreadPoolExecutor(max_workers=max(1, min(int(workers), len(tasks) or 1))) as pool:
                rendered_list = list(pool.map(lambda item: self._render_image(item[1]), tasks))
        except Exception:  # noqa: BLE001
            self.log.exception("并行解码表情失败，回退串行")
            rendered_list = [self._render_image(frame) for _state, frame in tasks]
        for (state, frame_name), rendered in zip(tasks, rendered_list):
            if rendered is None:
                failed.append(f"{state}:{frame_name}")
                continue
            try:
                rgb, mask = rendered
                photo = ImageTk.PhotoImage(rgb, master=None)
                width = photo.width()
                if width <= 0:
                    failed.append(f"{state}:{frame_name}:zero_width")
                    continue
                created += 1
                if populate:
                    self._cache.setdefault(state, {})[frame_name] = (photo, mask)
                else:
                    del photo
            except Exception:  # noqa: BLE001
                failed.append(f"{state}:{frame_name}:photo_error")
        if populate:
            for state in self.manifest.state_names():
                if state in self._cache:
                    self._cache.move_to_end(state)
            self._evict()
        return {"created": created, "failed": failed}
