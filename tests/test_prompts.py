"""提示词 / 本地兜底短句 / 截断测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import constants as C  # noqa: E402
import prompts  # noqa: E402

INTERACTION_CATEGORIES = (
    "poke",
    "greet",
    "drag",
    "resize",
    "sleep",
    "wake",
    "chat_no_key",
    "chat_error",
    "first_run",
)


class PromptsTest(unittest.TestCase):
    def test_each_interaction_has_at_least_8_lines(self) -> None:
        for category in INTERACTION_CATEGORIES:
            with self.subTest(category=category):
                lines = list(prompts.all_lines(category))
                self.assertGreaterEqual(len(lines), 8, category)
                self.assertEqual(len(set(lines)), len(lines), f"{category} 存在重复短句")

    def test_local_lines_fit_default_max_chars(self) -> None:
        for category, lines in prompts.LOCAL_LINES.items():
            for line in lines:
                self.assertLessEqual(len(line), C.DEFAULT_MAX_CHARS, f"{category}: {line}")
                self.assertGreater(len(line), 0)

    def test_random_line_known_and_unknown(self) -> None:
        for _ in range(20):
            self.assertIn(prompts.random_line("poke"), prompts.LOCAL_LINES["poke"])
        self.assertTrue(prompts.random_line("no_such_category"))

    def test_truncate_text(self) -> None:
        self.assertEqual(prompts.truncate_text("短句", 60), "短句")
        long_text = "鲸" * 100
        truncated = prompts.truncate_text(long_text, 60)
        self.assertEqual(len(truncated), 60)
        self.assertTrue(truncated.endswith("…"))
        self.assertEqual(prompts.truncate_text("", 60), "")

    def test_normalize_reply_collapses_whitespace(self) -> None:
        text = "  你好呀\n\n今天也要\n开心哦\t(๑•̀ㅂ•́)و✧  "
        normalized = prompts.normalize_reply(text)
        self.assertEqual(normalized, "你好呀 今天也要 开心哦 (๑•̀ㅂ•́)و✧")

    def test_clean_and_truncate(self) -> None:
        text = "一" * 50 + "\n\n" + "二" * 50
        out = prompts.clean_and_truncate(text, 60)
        self.assertLessEqual(len(out), 60)
        self.assertNotIn("\n", out)

    def test_system_prompt_contains_rules_and_persona(self) -> None:
        prompt = prompts.build_system_prompt(None, 60)
        self.assertIn(prompts.DEFAULT_PERSONA, prompt)
        self.assertIn("60", prompt)
        self.assertIn("1~2 句", prompt)
        self.assertIn("颜文字", prompt)
        # 自定义人设生效
        custom = prompts.build_system_prompt("你是一只小鲨鱼", 40)
        self.assertIn("你是一只小鲨鱼", custom)
        self.assertIn("40", custom)
        # 占位符解析为默认人设
        self.assertEqual(prompts.resolve_persona(prompts.PERSONA_PLACEHOLDER), prompts.DEFAULT_PERSONA)
        self.assertEqual(prompts.resolve_persona(""), prompts.DEFAULT_PERSONA)

    def test_error_reply_covers_all_kinds(self) -> None:
        for kind in prompts.ERROR_INFO:
            bubble_line, detail = prompts.error_reply(kind)
            self.assertTrue(bubble_line)
            self.assertTrue(detail)
            self.assertLessEqual(len(bubble_line), 80)
        # 未知 kind 有兜底
        self.assertTrue(prompts.error_reply("unknown-kind")[0])

    def test_required_states_constant(self) -> None:
        self.assertEqual(len(C.REQUIRED_STATES), 14)
        self.assertEqual(len(set(C.REQUIRED_STATES)), 14)
        # 常用表情有对应本地情绪短句分类
        for category in ("poke", "sleep", "wake", "drag"):
            self.assertIn(category, prompts.LOCAL_LINES)


if __name__ == "__main__":
    unittest.main()
