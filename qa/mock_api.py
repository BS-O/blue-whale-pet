"""本地 DeepSeek API Mock（Lead QA）——用于无真实 Key 时端到端验证聊天/流式解析。

模拟 OpenAI 兼容接口:
  GET  /models
  POST /chat/completions   (stream=true → SSE；否则普通 JSON)
非法/缺失 Authorization → 401；带 "quota" 关键词 → 402；带 "ratelimit" → 429。

用法:
  py qa/mock_api.py --port 8765 [--reply "你好呀！我是大肥鱼~"]
  # 桌宠设置里 base_url 填 http://127.0.0.1:8765 ，API Key 随便填
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:  # Windows 控制台默认 GBK，避免打印颜文字崩溃
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

REPLY = "嘿嘿，我是蓝色大肥鱼～今天也要开心哦 (๑•̀ㅂ•́)و✧"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: A003
        print("[mock]", fmt % args, flush=True)

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/models"):
            return self._json(200, {"object": "list", "data": [
                {"id": "deepseek-flash", "object": "model"},
                {"id": "deepseek-v4-pro", "object": "model"}]})
        if self.path.startswith("/_stats"):
            return self._json(200, self.server.stats)  # type: ignore[attr-defined]
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        try:
            req = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": {"message": "bad json"}})
        auth = self.headers.get("Authorization", "")
        if not auth.lower().startswith("bearer ") or auth.strip().lower() in ("bearer", "bearer "):
            self.server.stats["unauthorized"] += 1  # type: ignore[attr-defined]
            return self._json(401, {"error": {"message": "Authentication Fails (no such user)"}})
        self.server.stats["completions"] += 1  # type: ignore[attr-defined]
        if req.get("stream"):
            self.server.stats["stream"] += 1  # type: ignore[attr-defined]
        self.server.stats["last_model"] = req.get("model")  # type: ignore[attr-defined]
        self.server.stats["last_messages"] = req.get("messages", [])[-6:]  # type: ignore[attr-defined]
        content = json.dumps(req, ensure_ascii=False)
        if "quota" in content:
            return self._json(402, {"error": {"message": "Insufficient Balance"}})
        if "ratelimit" in content:
            return self._json(429, {"error": {"message": "Rate limit reached"}})
        model = req.get("model", "deepseek-flash")
        reply = self.server.reply  # type: ignore[attr-defined]
        usage = {"prompt_tokens": 42, "completion_tokens": max(1, len(reply) // 2), "total_tokens": 42 + max(1, len(reply) // 2)}
        if not req.get("stream"):
            return self._json(200, {
                "id": "mock-1", "object": "chat.completion", "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
                "usage": usage})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def chunk(data: str) -> None:
            payload = data.encode()
            self.wfile.write(f"{len(payload):X}\r\n".encode() + payload + b"\r\n")
            self.wfile.flush()

        chunk(": keep-alive\n\n")
        # 分 3~6 个 token 块返回，模拟真实流式
        step = max(1, len(reply) // 5)
        parts = [reply[i:i + step] for i in range(0, len(reply), step)]
        for i, part in enumerate(parts):
            obj = {"id": "mock-1", "object": "chat.completion.chunk", "created": int(time.time()), "model": model,
                   "choices": [{"index": 0, "delta": {"role": "assistant", "content": part} if i == 0 else {"content": part},
                                "finish_reason": None}]}
            chunk(f"data: {json.dumps(obj, ensure_ascii=False)}\n\n")
            time.sleep(0.12)
        finish = {"id": "mock-1", "object": "chat.completion.chunk", "created": int(time.time()), "model": model,
                  "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": usage}
        chunk(f"data: {json.dumps(finish, ensure_ascii=False)}\n\n")
        chunk("data: [DONE]\n\n")
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--reply", default=REPLY)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    srv.reply = args.reply  # type: ignore[attr-defined]
    srv.stats = {"completions": 0, "stream": 0, "unauthorized": 0,
                 "last_model": None, "last_messages": []}  # type: ignore[attr-defined]
    print(f"mock DeepSeek API listening on http://127.0.0.1:{args.port}  reply={args.reply!r}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
