"""资产清单与资源路径测试（读取真实 assets/，校验 SPEC §4 契约）。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import constants as C  # noqa: E402
import resources  # noqa: E402
from anim.manifest import Manifest  # noqa: E402


class RealManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.path = resources.manifest_path()
        if not self.path.is_file():
            self.skipTest("assets/mascot/manifest.json 不存在（资产生成中）")
        self.manifest = Manifest.load(self.path)

    def test_required_states_present(self) -> None:
        for state in C.REQUIRED_STATES:
            self.assertIn(state, self.manifest.states, f"缺少表情: {state}")
        self.assertEqual(self.manifest.required_missing, [])

    def test_canvas_contract(self) -> None:
        self.assertEqual(self.manifest.canvas_w, 512)
        self.assertEqual(self.manifest.canvas_h, 512)
        self.assertEqual(self.manifest.anchor_x, 256)
        self.assertEqual(self.manifest.anchor_y, 496)
        self.assertEqual(self.manifest.key_color.lower(), "#010203")

    def test_each_state_has_2_to_5_frames(self) -> None:
        for state, info in self.manifest.states.items():
            frames = info["frames"]
            self.assertGreaterEqual(len(frames), 2, state)
            self.assertLessEqual(len(frames), 5, state)
            self.assertEqual(len(frames), len(info["durations"]), state)
            for duration in info["durations"]:
                self.assertGreater(duration, 0, state)
                self.assertLessEqual(duration, 3000, state)

    def test_all_frames_exist_and_rgba(self) -> None:
        from PIL import Image

        missing = self.manifest.missing_frames()
        self.assertEqual(missing, [], f"缺帧: {missing[:8]}")
        for state in self.manifest.states:
            for frame in self.manifest.frames(state):
                path = self.manifest.frame_path(frame)
                with Image.open(path) as image:
                    self.assertEqual(image.size, (512, 512), str(path))
                    self.assertIn(image.mode, ("RGBA", "LA", "P"), str(path))

    def test_default_state(self) -> None:
        self.assertEqual(self.manifest.default_state, "idle")
        self.assertTrue(self.manifest.loop("idle"))
        self.assertGreater(self.manifest.frame_total, 0)

    def test_icons_exist(self) -> None:
        icons = resources.asset_root() / "icons"
        if not icons.is_dir():
            self.skipTest("assets/icons 不存在（资产生成中）")
        self.assertTrue((icons / "app.ico").is_file())
        self.assertTrue((icons / "app.png").is_file())
        self.assertTrue((icons / "tray.ico").is_file())


class ResourcesTest(unittest.TestCase):
    def test_asset_root_dev_mode(self) -> None:
        self.assertFalse(resources.is_frozen())
        self.assertEqual(resources.asset_root(), resources.project_root() / "assets")
        self.assertEqual(resources.manifest_path(), resources.asset_root() / "mascot" / "manifest.json")

    def test_data_dir_env_override(self) -> None:
        with tempfile.TemporaryDirectory(prefix="res-data-") as tmp:
            old = resources.data_dir()
            try:
                resources.set_data_dir_override(tmp)
                self.assertEqual(resources.data_dir(), Path(tmp))
            finally:
                resources.set_data_dir_override(str(old))

    def test_resolve_config_path_nonexistent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="res-cfg-") as tmp:
            target = Path(tmp) / "sub" / "my-config.json"
            resolved, note = resources.resolve_config_path(str(target))
            self.assertEqual(resolved, target.resolve())
            self.assertEqual(note, "")

    def test_resolve_config_path_unwritable_falls_back(self) -> None:
        with tempfile.TemporaryDirectory(prefix="res-cfg-") as tmp:
            blocker = Path(tmp) / "blocked"
            blocker.write_text("not a directory", encoding="utf-8")
            target = blocker / "config.json"
            resolved, note = resources.resolve_config_path(str(target))
            self.assertNotEqual(resolved, target)
            self.assertTrue(note)

    def test_resolve_config_path_directory_falls_back(self) -> None:
        with tempfile.TemporaryDirectory(prefix="res-cfg-") as tmp:
            resolved, note = resources.resolve_config_path(tmp)
            self.assertTrue(note)
            self.assertTrue(str(resolved).endswith("config.json"))

    def test_launch_command_non_empty(self) -> None:
        command = resources.launch_command()
        self.assertGreaterEqual(len(command), 1)
        quoted = resources.quote_command(command)
        self.assertTrue(quoted.strip())

    def test_asset_report_keys(self) -> None:
        report = resources.asset_report()
        for key in ("asset_root", "manifest", "manifest_exists", "app_icon_exists"):
            self.assertIn(key, report)


if __name__ == "__main__":
    unittest.main()
