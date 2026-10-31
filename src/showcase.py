"""``--showcase [SECONDS]``：固定位置循环展示全部表情并显示名字（截图/验收用）。

- 可与 ``--config`` 组合（config.pet.size/x/y 生效，x/y 为逻辑像素）
- 到时自动退出；不写配置、不启用托盘/API，保证可脚本化
"""
from __future__ import annotations

import logging
import sys
import tkinter as tk
from pathlib import Path
from typing import Any

import anim
import config as config_module
import constants as C
import platform_win
import resources
from bubble import Bubble
from pet_window import PetWindow

logger = logging.getLogger("bluewhale.showcase")


class _NullCallbacks:
    """showcase 下宠物窗口无交互回调。"""


def run_showcase(
    seconds: float = 12.0,
    config_path: Path | None = None,
    logger_: logging.Logger | None = None,
) -> int:
    log = logger_ or logger
    seconds = max(1.0, min(600.0, float(seconds or 12.0)))
    path = config_path or resources.default_config_path()
    try:
        cfg, _info = config_module.load_or_create_config(path)
        platform_win.prepare_dpi()
        scale = platform_win.dpi_scale()
        manifest = anim.Manifest.load(resources.manifest_path())

        if platform_win.IS_WINDOWS:
            sprite_mode: str = "chroma"
            shaper = None
        else:
            import platform_linux

            shaper = platform_linux.XShape()
            sprite_mode = "shape" if shaper.available else "alpha"

        root = tk.Tk(className=C.WM_CLASS)
        root.withdraw()
        root.title(C.APP_NAME)
        platform_win.apply_tk_scaling(root)

        sprites = anim.SpriteCache(
            manifest,
            mode=sprite_mode,
            key_rgb=manifest.key_rgb,
            max_states=4,
            logger_=log,
        )
        pet = PetWindow(
            root,
            cfg,
            manifest,
            callbacks=_NullCallbacks(),
            scale=scale,
            sprite_mode=sprite_mode,
            shaper=shaper,
        )
        sprites.set_render_size(pet.pixel_w, pet.pixel_h)
        # 先渲染首帧再显示窗口，避免自动化脚本抓到空白窗口
        first_state = next((s for s in C.REQUIRED_STATES if manifest.has_state(s)), manifest.default_state)
        try:
            sprites.prepare(first_state)
            first_frames = manifest.frames(first_state)
            first_entry = sprites.get(first_state, first_frames[0]) if first_frames else None
            if first_entry is not None:
                pet.set_frame(first_entry[0], first_entry[1])
        except Exception:  # noqa: BLE001
            log.exception("showcase 首帧渲染失败")
        pet.show()
        root.update()
        log.info(
            "showcase 开始: %.1fs, size=%spx(物理), scale=%.2f, states=%d",
            seconds,
            pet.pixel_w,
            scale,
            len(manifest.states),
        )

        pet_rect = lambda: (pet.position()[0], pet.position()[1], pet.pixel_w, pet.pixel_h)  # noqa: E731
        bubble = Bubble(
            root,
            pet_rect_provider=pet_rect,
            scale=scale,
            mode=sprite_mode,
            key_rgb=manifest.key_rgb,
            shaper=shaper,
            logger_=log,
        )

        states = [state for state in C.REQUIRED_STATES if manifest.has_state(state)]
        states += [state for state in manifest.state_names() if state not in states]
        interval_ms = int(max(500, min(1500, (seconds * 1000.0) / (len(states) + 0.5))))
        counter = {"index": 0}
        closed = {"value": False}

        def show_state() -> None:
            if closed["value"] or not states:
                return
            state = states[counter["index"] % len(states)]
            counter["index"] += 1
            try:
                sprites.prepare(state)
                frames = manifest.frames(state)
                entry = sprites.get(state, frames[0]) if frames else None
                if entry is not None:
                    pet.set_frame(entry[0], entry[1])
                bubble.show(f"表情：{state}", seconds=min(3.0, seconds), typewriter=False)
            except Exception:  # noqa: BLE001
                log.exception("showcase 展示表情失败: %s", state)
            if counter["index"] < len(states):
                root.after(interval_ms, show_state)
            else:
                # 一轮结束后继续循环（剩余时间）
                counter["index"] = 0
                root.after(interval_ms, show_state)

        def finish() -> None:
            if closed["value"]:
                return
            closed["value"] = True
            log.info("showcase 结束")
            try:
                bubble.destroy()
            except Exception:  # noqa: BLE001
                pass
            try:
                pet.destroy()
            except Exception:  # noqa: BLE001
                pass
            if shaper is not None:
                try:
                    shaper.close()
                except Exception:  # noqa: BLE001
                    pass
            try:
                root.destroy()
            except tk.TclError:
                pass

        root.after(80, show_state)
        root.after(int(seconds * 1000), finish)
        root.protocol("WM_DELETE_WINDOW", finish)
        root.mainloop()
        return 0
    except tk.TclError as exc:
        log.error("showcase 无法创建窗口: %s", exc)
        sys.stderr.write(f"SHOWCASE FAIL 无法创建 Tk 窗口: {exc}\n")
        return 1
    except Exception as exc:  # noqa: BLE001
        log.exception("showcase 失败")
        sys.stderr.write(f"SHOWCASE FAIL {exc.__class__.__name__}: {exc}\n")
        return 1
