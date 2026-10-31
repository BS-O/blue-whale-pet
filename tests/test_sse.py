"""SSE 解析 / DeepSeek 请求构造测试（不联网）。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import api  # noqa: E402
import config  # noqa: E402
import constants as C  # noqa: E402


def sse_content(obj) -> bytes:
    return ("data: " + json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


class SSETest(unittest.TestCase):
    def test_parse_content_line(self) -> None:
        line = 'data: {"choices":[{"delta":{"content":"你好"}}]}'
        self.assertEqual(api.parse_sse_line(line), ("content", "你好"))

    def test_parse_done(self) -> None:
        self.assertEqual(api.parse_sse_line("data: [DONE]"), ("done", ""))

    def test_parse_ignores_comments_and_blank(self) -> None:
        self.assertIsNone(api.parse_sse_line(": keep-alive"))
        self.assertIsNone(api.parse_sse_line(""))
        self.assertIsNone(api.parse_sse_line("event: ping"))
        self.assertIsNone(api.parse_sse_line("data: not-json"))

    def test_parse_message_fallback(self) -> None:
        # 部分兼容实现用 message 而非 delta（非流式回包）
        line = 'data: {"choices":[{"message":{"content":"嗨"}}]}'
        self.assertEqual(api.parse_sse_line(line), ("content", "嗨"))

    def test_parse_error_payload_raises(self) -> None:
        line = 'data: {"error":{"message":"invalid api key","code":401}}'
        with self.assertRaises(api.ApiError) as ctx:
            api.parse_sse_line(line)
        self.assertEqual(ctx.exception.kind, "auth")

    def test_decoder_chunked_and_keepalive(self) -> None:
        decoder = api.SSEDecoder()
        events: list[tuple[str, str]] = []
        # "你" 的 UTF-8 为 3 字节，故意在序列中间切断 chunk；末尾用 \r\n
        first_line = 'data: {"choices":[{"delta":{"content":"你"}}]}'.encode("utf-8")
        split_at = first_line.index("你".encode("utf-8")) + 1
        events += decoder.feed(first_line[:split_at])
        events += decoder.feed(first_line[split_at:] + b"\r\n: ping\r\n\r\n")
        events += decoder.feed(sse_content({"choices": [{"delta": {"content": "好"}}]}))
        events += decoder.feed(b"data: [DONE]\n")
        events += decoder.flush()
        content = "".join(text for kind, text in events if kind == "content")
        self.assertEqual(content, "你好")
        self.assertTrue(any(kind == "done" for kind, _ in events))
        self.assertEqual(len([e for e in events if e[0] == "done"]), 1)

    def test_decoder_multiple_events_one_chunk(self) -> None:
        decoder = api.SSEDecoder()
        chunk = (
            sse_content({"choices": [{"delta": {"content": "A"}}]})
            + sse_content({"choices": [{"delta": {"content": "B"}}]})
            + b"data: [DONE]\n"
        )
        events = decoder.feed(chunk)
        self.assertEqual([e for e in events if e[0] == "content"], [("content", "A"), ("content", "B")])
        self.assertEqual(events[-1][0], "done")

    def test_decoder_flush_without_newline(self) -> None:
        decoder = api.SSEDecoder()
        line = 'data: {"choices":[{"delta":{"content":"尾"}}]}'.encode("utf-8")
        self.assertEqual(decoder.feed(line), [])
        self.assertEqual(decoder.flush(), [("content", "尾")])

    def test_empty_delta_ignored(self) -> None:
        self.assertIsNone(api.parse_sse_line('data: {"choices":[{"delta":{"content":""}}]}'))
        self.assertIsNone(api.parse_sse_line('data: {"choices":[{"delta":{"role":"assistant"}}]}'))

    def test_iter_sse_events_helper(self) -> None:
        lines = [
            ": keepalive",
            'data: {"choices":[{"delta":{"content":"1"}}]}',
            'data: {"choices":[{"delta":{"content":"2"}}]}',
            "data: [DONE]",
        ]
        events = list(api.iter_sse_events(lines))
        self.assertEqual([e[1] for e in events[:2]], ["1", "2"])
        self.assertEqual(events[-1][0], "done")


class RequestBuildTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = config.default_config()
        self.cfg["api"]["key"] = "sk-test"
        self.cfg["api"]["model"] = "deepseek-flash"

    def test_url(self) -> None:
        self.assertEqual(api.completions_url("https://api.deepseek.com"), "https://api.deepseek.com/chat/completions")
        self.assertEqual(
            api.completions_url("https://api.deepseek.com/"), "https://api.deepseek.com/chat/completions"
        )

    def test_payload_contract(self) -> None:
        payload = api.build_payload(self.cfg, [{"role": "user", "content": "hi"}], stream=True)
        self.assertEqual(payload["model"], "deepseek-flash")
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["max_tokens"], 120)
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertAlmostEqual(payload["temperature"], 1.3)
        self.assertEqual(payload["messages"][0]["content"], "hi")

    def test_headers_bearer(self) -> None:
        headers = api.build_headers(self.cfg)
        self.assertEqual(headers["Authorization"], "Bearer sk-test")
        self.assertIn("application/json", headers["Content-Type"])
        self.assertIn(C.APP_ID, headers["User-Agent"])
        # 无 key 时不带 Authorization
        self.cfg["api"]["key"] = ""
        self.assertNotIn("Authorization", api.build_headers(self.cfg))

    def test_build_request(self) -> None:
        request = api.build_request(self.cfg, [{"role": "user", "content": "hi"}], stream=False)
        self.assertEqual(request.full_url, "https://api.deepseek.com/chat/completions")
        body = json.loads(request.data.decode("utf-8"))
        self.assertFalse(body["stream"])
        self.assertEqual(request.get_header("Authorization"), "Bearer sk-test")

    def test_has_key(self) -> None:
        self.assertTrue(api.DeepSeekClient.has_key(self.cfg))
        self.cfg["api"]["key"] = "   "
        self.assertFalse(api.DeepSeekClient.has_key(self.cfg))

    def test_error_kind_map(self) -> None:
        self.assertEqual(api._kind_for_status(401), "auth")
        self.assertEqual(api._kind_for_status(402), "insufficient_balance")
        self.assertEqual(api._kind_for_status(429), "rate_limit")
        self.assertEqual(api._kind_for_status(502), "server")
        self.assertEqual(api._kind_for_status(418), "http")


class ChatSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = config.default_config()
        self.session = api.ChatSession(8)

    def test_context_keeps_recent_8_rounds(self) -> None:
        for i in range(12):
            self.session.add_turn(f"问题{i}", f"回答{i}")
        self.assertEqual(self.session.rounds, 8)
        messages = self.session.build_messages(self.cfg, "新问题")
        # system + 8 轮 * 2 + 当前 user
        self.assertEqual(len(messages), 1 + 16 + 1)
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("1~2 句", messages[0]["content"])
        self.assertEqual(messages[1]["content"], "问题4")
        self.assertEqual(messages[-1]["content"], "新问题")

    def test_clear(self) -> None:
        self.session.add_turn("a", "b")
        self.session.clear()
        self.assertEqual(self.session.rounds, 0)
        self.assertEqual(len(self.session.build_messages(self.cfg, "x")), 2)

    def test_history_copy_is_immutable(self) -> None:
        self.session.add_turn("a", "b")
        history = self.session.history
        history[0]["content"] = "被篡改"
        self.assertEqual(self.session.history[0]["content"], "a")


if __name__ == "__main__":
    unittest.main()
