"""动画状态机测试（注入假调度器，不依赖 Tk）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from anim.manifest import Manifest  # noqa: E402
from anim.state import Animator  # noqa: E402


MANIFEST_DATA = {
    "version": 1,
    "canvas": {"w": 512, "h": 512, "anchor_x": 256, "anchor_y": 496},
    "key_color": "#010203",
    "default_state": "idle",
    "states": {
        "idle": {"frames": ["idle_0", "idle_1"], "durations": [100, 100], "loop": True},
        "happy": {"frames": ["happy_0", "happy_1", "happy_2"], "durations": [50, 60, 70], "loop": False},
        "talk": {"frames": ["talk_0", "talk_1"], "durations": [80, 80], "loop": True},
        "blink": {"frames": ["blink_0"], "durations": [40], "loop": False},
    },
}


class FakeScheduler:
    def __init__(self) -> None:
        self.tasks: list[tuple[int, object]] = []
        self.cancelled = 0

    def __call__(self, delay: int, callback) -> int:
        self.tasks.append((delay, callback))
        return len(self.tasks)

    def run_next(self, limit: int = 100):
        self.assert_some(limit)
        delay, callback = self.tasks.pop(0)
        callback()
        return delay

    def assert_some(self, limit: int = 100) -> None:
        if not self.tasks:
            raise AssertionError("调度队列为空")

    def run_for(self, steps: int) -> list[int]:
        delays = []
        for _ in range(steps):
            if not self.tasks:
                break
            delays.append(self.run_next())
        return delays


class AnimatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = Manifest(MANIFEST_DATA)
        self.scheduler = FakeScheduler()
        self.frames: list[tuple[str, str, int]] = []
        self.animator = Animator(
            self.manifest,
            schedule=self.scheduler,
            on_frame=lambda state, frame, dur: self.frames.append((state, frame, dur)),
        )

    def test_play_emits_first_frame_immediately(self) -> None:
        self.animator.play("happy")
        self.assertEqual(self.animator.current_state, "happy")
        self.assertEqual(self.frames, [("happy", "happy_0", 50)])
        self.assertEqual(self.scheduler.tasks[0][0], 50)

    def test_frame_sequence_and_end_fallback(self) -> None:
        self.animator.play("happy")
        self.scheduler.run_next()  # -> happy_1
        self.scheduler.run_next()  # -> happy_2
        self.scheduler.run_next()  # 结束 -> fallback idle_0
        self.assertEqual(
            [(state, frame) for state, frame, _ in self.frames],
            [("happy", "happy_0"), ("happy", "happy_1"), ("happy", "happy_2"), ("idle", "idle_0")],
        )
        self.assertEqual(self.animator.current_state, "idle")

    def test_on_end_callback_can_handle(self) -> None:
        ended: list[str] = []

        def on_end(state: str) -> bool:
            ended.append(state)
            self.animator.play("talk", loop=True)
            return True

        self.animator.play("blink", loop=False, on_end=on_end)
        self.scheduler.run_next()  # blink 单帧结束 -> on_end
        self.assertEqual(ended, ["blink"])
        self.assertEqual(self.animator.current_state, "talk")

    def test_on_end_false_uses_fallback(self) -> None:
        ended: list[str] = []
        self.animator.play("blink", loop=False, on_end=lambda state: ended.append(state) or False)
        self.scheduler.run_next()
        self.assertEqual(ended, ["blink"])
        self.assertEqual(self.animator.current_state, "idle")

    def test_loop_state_cycles_forever(self) -> None:
        self.animator.play("talk", loop=True)
        delays = self.scheduler.run_for(5)
        states = [frame for _state, frame, _ in self.frames]
        self.assertEqual(states[:3], ["talk_0", "talk_1", "talk_0"])
        self.assertEqual(self.animator.current_state, "talk")
        self.assertTrue(delays)
        self.assertTrue(self.animator.playing)

    def test_invalid_state_falls_back(self) -> None:
        hit = self.animator.play("not-a-state")
        self.assertFalse(hit)
        self.assertEqual(self.animator.current_state, "idle")
        self.assertEqual(self.frames[-1][1], "idle_0")

    def test_stale_callback_ignored_after_new_play(self) -> None:
        self.animator.play("happy")
        stale = self.scheduler.tasks.pop(0)
        self.animator.play("talk", loop=True)
        frames_before = len(self.frames)
        stale[1]()  # 旧代际回调应被忽略
        self.assertEqual(len(self.frames), frames_before)
        self.assertEqual(self.animator.current_state, "talk")

    def test_stop_prevents_further_frames(self) -> None:
        self.animator.play("happy")
        self.animator.stop()
        frames_before = len(self.frames)
        self.scheduler.run_for(5)
        self.assertEqual(len(self.frames), frames_before)
        self.assertFalse(self.animator.playing)

    def test_manifest_loop_default(self) -> None:
        self.animator.play("talk")
        self.assertTrue(self.animator.loop)
        self.animator.play("happy")
        self.assertFalse(self.animator.loop)

    def test_on_frame_exception_does_not_break(self) -> None:
        def bad_frame(state: str, frame: str, dur: int) -> None:
            raise RuntimeError("boom")

        animator = Animator(self.manifest, schedule=self.scheduler, on_frame=bad_frame)
        animator.play("happy")
        self.scheduler.run_next()
        self.assertEqual(animator.current_state, "happy")

    def test_custom_durations_respected(self) -> None:
        self.animator.play("happy")
        self.assertEqual(self.scheduler.tasks[0][0], 50)
        self.scheduler.run_next()
        self.assertEqual(self.scheduler.tasks[0][0], 60)
        self.scheduler.run_next()
        self.assertEqual(self.scheduler.tasks[0][0], 70)


class ManifestDataTest(unittest.TestCase):
    def test_manifest_normalizes_durations(self) -> None:
        data = {
            "canvas": {"w": 100, "h": 200},
            "default_state": "unknown",
            "states": {
                "idle": {"frames": ["a"], "durations": [0]},
                "wave": {"frames": ["w0", "w1"], "durations": [200], "loop": True},
            },
        }
        manifest = Manifest(data)
        self.assertEqual(manifest.default_state, "idle")
        self.assertEqual(manifest.durations("idle"), [16])  # 最小 16ms
        self.assertEqual(manifest.durations("wave"), [200, 300])  # 缺省补 300
        self.assertEqual(manifest.aspect, 2.0)
        self.assertEqual(manifest.frame_count(), 3)
        self.assertEqual(manifest.required_missing[0], "blink")

    def test_bad_manifest_raises(self) -> None:
        with self.assertRaises(Exception):
            Manifest({})
        with self.assertRaises(Exception):
            Manifest({"canvas": {"w": -1, "h": 10}, "states": {"idle": {"frames": ["a"]}}})

    def test_state_without_frames_ignored(self) -> None:
        manifest = Manifest(
            {
                "canvas": {"w": 10, "h": 10},
                "states": {"idle": {"frames": ["a"]}, "broken": {"frames": []}},
            }
        )
        self.assertIn("idle", manifest.states)
        self.assertNotIn("broken", manifest.states)


if __name__ == "__main__":
    unittest.main()
