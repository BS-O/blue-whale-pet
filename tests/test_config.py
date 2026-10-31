"""配置模块测试：默认值/深合并/校验/原子写/损坏恢复。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import config  # noqa: E402
import constants as C  # noqa: E402


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="cfg-test-")
        self.path = Path(self.tmp.name) / "config.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_defaults_contract(self) -> None:
        cfg = config.default_config()
        self.assertEqual(cfg["version"], 1)
        self.assertEqual(cfg["api"]["model"], "deepseek-flash")
        self.assertEqual(cfg["api"]["max_tokens"], 120)
        self.assertEqual(cfg["api"]["base_url"], "https://api.deepseek.com")
        self.assertEqual(cfg["pet"]["size"], 168)
        self.assertEqual(cfg["speech"]["max_chars"], 60)
        self.assertEqual(cfg["behavior"]["auto_sleep_seconds"], 180)
        self.assertFalse(cfg["system"]["autostart"])
        self.assertTrue(cfg["pet"]["always_on_top"])

    def test_roundtrip_keeps_unicode(self) -> None:
        cfg = config.default_config()
        cfg["api"]["key"] = "sk-test-123"
        cfg["speech"]["persona"] = "你是一只爱吃小鱼干的蓝鲸～"
        cfg["pet"]["size"] = 240
        cfg["pet"]["x"] = 120
        cfg["pet"]["y"] = -40
        self.assertTrue(config.save_config(self.path, cfg))
        loaded, info = config.load_config(self.path)
        self.assertTrue(info["existed"])
        self.assertFalse(info["recovered"])
        self.assertEqual(loaded["api"]["key"], "sk-test-123")
        self.assertEqual(loaded["speech"]["persona"], "你是一只爱吃小鱼干的蓝鲸～")
        self.assertEqual(loaded["pet"]["size"], 240)
        self.assertEqual(loaded["pet"]["x"], 120)
        self.assertEqual(loaded["pet"]["y"], -40)

    def test_missing_file_returns_defaults(self) -> None:
        cfg, info = config.load_config(self.path)
        self.assertTrue(info["created"])
        self.assertEqual(cfg["pet"]["size"], 168)

    def test_partial_override_deep_merge(self) -> None:
        self.path.write_text(json.dumps({"pet": {"size": 240, "x": 120, "y": 240}}), encoding="utf-8")
        cfg, _info = config.load_config(self.path)
        self.assertEqual(cfg["pet"]["size"], 240)
        self.assertEqual(cfg["pet"]["x"], 120)
        self.assertEqual(cfg["pet"]["y"], 240)
        # 其它字段保持默认
        self.assertEqual(cfg["api"]["model"], "deepseek-flash")
        self.assertTrue(cfg["pet"]["always_on_top"])

    def test_corrupt_config_backed_up(self) -> None:
        self.path.write_text("{not valid json", encoding="utf-8")
        cfg, info = config.load_config(self.path)
        self.assertTrue(info["recovered"])
        backup = Path(str(info["backup"]))
        self.assertTrue(backup.is_file())
        self.assertEqual(cfg["pet"]["size"], 168)
        # 备份内容保留原始损坏文本
        self.assertIn("not valid json", backup.read_text(encoding="utf-8"))

    def test_normalize_clamps_and_fixes(self) -> None:
        cfg, warnings = config.normalize_config(
            {
                "api": {"base_url": "ftp://bad", "model": "", "max_tokens": 99999, "temperature": 9},
                "pet": {"size": 9999, "opacity": 5, "x": "abc"},
                "speech": {"max_chars": 1},
                "behavior": {"auto_sleep_seconds": -5},
            }
        )
        self.assertEqual(cfg["pet"]["size"], C.MAX_SIZE)
        self.assertEqual(cfg["api"]["max_tokens"], 2048)
        self.assertEqual(cfg["api"]["temperature"], 2.0)
        self.assertEqual(cfg["api"]["base_url"], C.DEFAULT_BASE_URL)
        self.assertEqual(cfg["api"]["model"], C.DEFAULT_MODEL)
        self.assertEqual(cfg["pet"]["opacity"], 1.0)
        self.assertIsNone(cfg["pet"]["x"])
        self.assertEqual(cfg["speech"]["max_chars"], 10)
        self.assertEqual(cfg["behavior"]["auto_sleep_seconds"], 0)
        self.assertTrue(warnings)

    def test_unknown_keys_dropped(self) -> None:
        cfg, _ = config.normalize_config({"pet": {"size": 200, "nonsense": 1}, "foo": "bar"})
        self.assertNotIn("nonsense", cfg["pet"])
        self.assertNotIn("foo", cfg)

    def test_atomic_write_no_temp_left(self) -> None:
        cfg = config.default_config()
        self.assertTrue(config.save_config(self.path, cfg))
        leftovers = [p.name for p in self.path.parent.iterdir() if p.name != "config.json"]
        self.assertEqual(leftovers, [])
        # 文件本身是合法 JSON
        json.loads(self.path.read_text(encoding="utf-8"))

    def test_load_or_create_persists(self) -> None:
        cfg, info = config.load_or_create_config(self.path)
        self.assertTrue(self.path.is_file())
        self.assertTrue(info["created"])
        self.assertEqual(cfg["version"], 1)

    def test_bool_coercion(self) -> None:
        cfg, _ = config.normalize_config(
            {"pet": {"always_on_top": "false", "click_through": 1}, "behavior": {"idle_animation": "no"}}
        )
        self.assertFalse(cfg["pet"]["always_on_top"])
        self.assertTrue(cfg["pet"]["click_through"])
        self.assertFalse(cfg["behavior"]["idle_animation"])

    # ------------------------------------------------------------------
    # API 平台（DeepSeek / GLM）
    # ------------------------------------------------------------------
    def test_provider_defaults(self) -> None:
        cfg, _ = config.normalize_config({})
        self.assertEqual(cfg["api"]["provider"], "deepseek")
        self.assertIn("deepseek", cfg["api"]["keys"])
        self.assertIn("glm", cfg["api"]["keys"])
        eff = config.effective_api(cfg)
        self.assertEqual(eff["provider"], "deepseek")
        self.assertEqual(eff["base_url"], "https://api.deepseek.com")

    def test_provider_invalid_falls_back(self) -> None:
        cfg, warnings = config.normalize_config({"api": {"provider": "openai"}})
        self.assertEqual(cfg["api"]["provider"], "deepseek")
        self.assertTrue(any("平台" in w for w in warnings))

    def test_glm_key_resolved_per_provider(self) -> None:
        raw = {"api": {"provider": "glm", "keys": {"deepseek": "sk-ds", "glm": "glm-key-x"}}}
        cfg, _ = config.normalize_config(raw)
        eff = config.effective_api(cfg)
        self.assertEqual(eff["provider"], "glm")
        self.assertEqual(eff["key"], "glm-key-x")
        # legacy key 迁移：旧配置只有 api.key → 视为 DeepSeek
        cfg2, _ = config.normalize_config({"api": {"key": "sk-legacy"}})
        self.assertEqual(config.effective_api(cfg2)["key"], "sk-legacy")
        self.assertEqual(cfg2["api"]["keys"]["deepseek"], "sk-legacy")

    def test_glm_payload_shape(self) -> None:
        import api as api_module

        raw = {"api": {"provider": "glm", "model": "glm-4.6", "keys": {"glm": "k"}}}
        cfg, _ = config.normalize_config(raw)
        payload = api_module.build_payload(cfg, [{"role": "user", "content": "hi"}], stream=True)
        self.assertEqual(payload["model"], "glm-4.6")
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        headers = api_module.build_headers(cfg)
        self.assertEqual(headers["Authorization"], "Bearer k")


if __name__ == "__main__":
    unittest.main()
