"""CLI 参数解析与入口常量测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import cli  # noqa: E402
import constants as C  # noqa: E402


class CliTest(unittest.TestCase):
    def test_no_args(self) -> None:
        opts = cli.parse_args([])
        self.assertFalse(opts.version)
        self.assertFalse(opts.selftest)
        self.assertIsNone(opts.showcase)
        self.assertIsNone(opts.config)
        self.assertFalse(opts.debug)
        self.assertFalse(opts.dump_config)

    def test_version(self) -> None:
        self.assertTrue(cli.parse_args(["--version"]).version)

    def test_selftest_debug(self) -> None:
        opts = cli.parse_args(["--selftest", "--debug"])
        self.assertTrue(opts.selftest)
        self.assertTrue(opts.debug)

    def test_config_path(self) -> None:
        opts = cli.parse_args(["--config", r"E:\tmp\my.json"])
        self.assertEqual(opts.config, r"E:\tmp\my.json")

    def test_showcase_default(self) -> None:
        self.assertEqual(cli.parse_args(["--showcase"]).showcase, 12.0)

    def test_showcase_seconds(self) -> None:
        self.assertEqual(cli.parse_args(["--showcase", "14"]).showcase, 14.0)
        self.assertEqual(cli.parse_args(["--showcase", "0.5"]).showcase, 1.0)  # 下限 1s
        self.assertEqual(cli.parse_args(["--showcase", "nonsense"]).showcase, 12.0)
        self.assertEqual(cli.parse_args(["--showcase", "9999"]).showcase, 600.0)

    def test_dump_config(self) -> None:
        self.assertTrue(cli.parse_args(["--dump-config"]).dump_config)

    def test_combined(self) -> None:
        opts = cli.parse_args(["--showcase", "14", "--config", "cfg.json", "--debug"])
        self.assertEqual(opts.showcase, 14.0)
        self.assertEqual(opts.config, "cfg.json")
        self.assertTrue(opts.debug)

    def test_unknown_arg_exits(self) -> None:
        with self.assertRaises(SystemExit):
            cli.parse_args(["--no-such-option"])

    def test_constants_contract(self) -> None:
        self.assertEqual(C.APP_VERSION, "1.0.0")
        self.assertEqual(C.APP_NAME, "蓝色大肥鱼")
        self.assertEqual(C.APP_ID, "BlueWhalePet")
        self.assertEqual(C.APP_PACKAGE, "blue-whale-pet")
        self.assertEqual(C.MIN_SIZE, 64)
        self.assertEqual(C.MAX_SIZE, 320)
        self.assertEqual(C.DEFAULT_MODEL, "deepseek-flash")
        self.assertIn("deepseek-v4-pro", C.MODEL_CHOICES)
        self.assertIn("glm", C.PROVIDERS)
        self.assertEqual(len(C.REQUIRED_STATES), 14)
        self.assertEqual(len(C.SIZE_PRESETS), 3)


if __name__ == "__main__":
    unittest.main()
