"""表情动画包：manifest 解析 + 帧缓存 + 动画状态机。

本包内模块均为绝对导入（``from anim.xxx import ...``），可被 src/main.py
作为独立脚本运行时正常加载。
"""
from __future__ import annotations

from anim.frames import SpriteCache, alpha_to_mask_bytes, default_sprite_mode
from anim.manifest import Manifest, ManifestError
from anim.state import Animator

__all__ = [
    "Animator",
    "Manifest",
    "ManifestError",
    "SpriteCache",
    "alpha_to_mask_bytes",
    "default_sprite_mode",
]
