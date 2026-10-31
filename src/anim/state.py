"""表情动画状态机（SPEC §6：切换全部表情、待机/眨眼/睡觉）。

设计为可测试：不直接依赖 Tk，定时器通过注入的 ``schedule(delay_ms, callback)``
调度（生产环境传 ``root.after``，测试传假调度器）。通过代际计数（generation）
丢弃过期回调，切换状态时无需显式取消定时器。
"""
from __future__ import annotations

import logging
from typing import Callable

from anim.manifest import Manifest

logger = logging.getLogger("bluewhale.anim.state")

Schedule = Callable[[int, Callable[[], None]], object]
FrameCallback = Callable[[str, str, int], None]
EndCallback = Callable[[str], bool | None]


class Animator:
    """按 manifest 的 durations 逐帧播放表情；非循环表情结束后回到默认表情。"""

    def __init__(
        self,
        manifest: Manifest,
        schedule: Schedule,
        on_frame: FrameCallback,
        fallback_state: str | None = None,
        logger_: logging.Logger | None = None,
    ) -> None:
        self.manifest = manifest
        self.schedule = schedule
        self.on_frame = on_frame
        self.log = logger_ or logger
        self.fallback_state = fallback_state or manifest.default_state
        self.current_state: str = manifest.default_state
        self.frame_index = 0
        self.loop = False
        self.playing = False
        self._gen = 0
        self._on_end: EndCallback | None = None

    # ------------------------------------------------------------------
    def set_fallback(self, state: str) -> None:
        if self.manifest.has_state(state):
            self.fallback_state = state

    def play(
        self,
        state: str,
        loop: bool | None = None,
        on_end: EndCallback | None = None,
    ) -> bool:
        """开始播放表情。非法 state 回退默认表情。返回是否命中 manifest。"""
        hit = self.manifest.has_state(state)
        if not hit:
            self.log.debug("未知表情 %r，回退 %s", state, self.fallback_state)
            state = self.fallback_state
        self._gen += 1
        gen = self._gen
        self.current_state = state
        self.frame_index = 0
        self.loop = self.manifest.loop(state) if loop is None else bool(loop)
        self._on_end = on_end
        self.playing = True
        self._emit(gen)
        return hit

    def stop(self) -> None:
        """停止播放（不再触发任何回调）。"""
        self._gen += 1
        self.playing = False
        self._on_end = None

    def is_state(self, state: str) -> bool:
        return self.current_state == state

    # ------------------------------------------------------------------
    def _emit(self, gen: int) -> None:
        if gen != self._gen:
            return
        frames = self.manifest.frames(self.current_state)
        durations = self.manifest.durations(self.current_state)
        index = min(self.frame_index, len(frames) - 1)
        frame_name = frames[index]
        duration = durations[index] if index < len(durations) else 300
        try:
            self.on_frame(self.current_state, frame_name, duration)
        except Exception:  # noqa: BLE001 - UI 回调异常不应中断动画
            self.log.exception("on_frame 回调异常 state=%s frame=%s", self.current_state, frame_name)
        self.schedule(max(16, int(duration)), lambda: self._advance(gen))

    def _advance(self, gen: int) -> None:
        if gen != self._gen:
            return
        frames = self.manifest.frames(self.current_state)
        next_index = self.frame_index + 1
        if next_index >= len(frames):
            if self.loop:
                next_index = 0
            else:
                self.playing = False
                self.frame_index = len(frames) - 1
                callback = self._on_end
                self._on_end = None
                handled: bool | None = False
                if callback is not None:
                    try:
                        handled = callback(self.current_state)
                    except Exception:  # noqa: BLE001
                        self.log.exception("on_end 回调异常 state=%s", self.current_state)
                        handled = False
                if not handled:
                    self.play(self.fallback_state)
                return
        self.frame_index = next_index
        self._emit(gen)
