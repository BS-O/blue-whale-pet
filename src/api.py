"""DeepSeek API 客户端（SPEC §3、§6；Lead 契约：OpenAI 兼容 + SSE 流式）。

- 仅使用标准库 urllib.request，禁止 requests
- POST {base_url}/chat/completions，Bearer 鉴权，stream=true
- ``thinking: {"type": "disabled"}`：桌宠要秒回，不要思考链
- 解析 SSE：``data: {...choices[0].delta.content}`` 与 ``data: [DONE]``
- 错误映射为 :class:`ApiError`（auth / insufficient_balance / rate_limit / timeout / network / server / http / bad_response / no_key）
- 会话上下文仅保留最近 8 轮
"""
from __future__ import annotations

import codecs
import json
import logging
import socket
import ssl
import urllib.error
import urllib.request
from collections import deque
from typing import Any, Iterable, Iterator

import constants as C
import prompts

logger = logging.getLogger("bluewhale.api")

CHAT_COMPLETIONS_PATH = "/chat/completions"


class ApiError(Exception):
    """API 调用异常，kind 用于本地兜底短句映射。"""

    def __init__(self, kind: str, message: str = "", status: int | None = None):
        super().__init__(message or kind)
        self.kind = kind
        self.message = message or kind
        self.status = status


# ---------------------------------------------------------------------------
# 请求构造
# ---------------------------------------------------------------------------

def completions_url(base_url: str) -> str:
    base = (base_url or C.DEFAULT_BASE_URL).strip().rstrip("/")
    return base + CHAT_COMPLETIONS_PATH


def effective_provider(cfg: dict[str, Any]) -> str:
    """当前生效的 API 平台 id（deepseek / glm），未知回退默认。"""
    api = cfg.get("api", {}) if isinstance(cfg, dict) else {}
    provider = str(api.get("provider") or C.DEFAULT_PROVIDER).lower()
    return provider if provider in C.PROVIDERS else C.DEFAULT_PROVIDER


def effective_key(cfg: dict[str, Any]) -> str:
    """按平台取 Key：优先 api.keys[provider]，兼容旧 api.key 字段。"""
    api = cfg.get("api", {}) if isinstance(cfg, dict) else {}
    provider = effective_provider(cfg)
    keys = api.get("keys") if isinstance(api.get("keys"), dict) else {}
    return str(keys.get(provider) or api.get("key") or "").strip()


def build_payload(cfg: dict[str, Any], messages: list[dict[str, str]], stream: bool = True) -> dict[str, Any]:
    """构造 OpenAI 兼容请求体（thinking 按平台预设注入）。"""
    api = cfg.get("api", {}) if isinstance(cfg, dict) else {}
    preset = C.PROVIDERS.get(effective_provider(cfg)) or C.PROVIDERS[C.DEFAULT_PROVIDER]
    payload: dict[str, Any] = {
        "model": api.get("model") or preset["default_model"],
        "messages": messages,
        "stream": bool(stream),
        "max_tokens": int(api.get("max_tokens") or 120),
        "temperature": float(api.get("temperature", 1.3)),
    }
    if preset.get("apply_thinking"):
        payload["thinking"] = {"type": "disabled"}
    return payload


def build_headers(cfg: dict[str, Any]) -> dict[str, str]:
    api = cfg.get("api", {}) if isinstance(cfg, dict) else {}
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if True else "application/json",
        "User-Agent": f"{C.APP_ID}/{C.APP_VERSION}",
    }
    key = effective_key(cfg)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def build_request(cfg: dict[str, Any], messages: list[dict[str, str]], stream: bool = True) -> urllib.request.Request:
    api = cfg.get("api", {}) if isinstance(cfg, dict) else {}
    url = completions_url(api.get("base_url") or C.DEFAULT_BASE_URL)
    body = json.dumps(build_payload(cfg, messages, stream=stream), ensure_ascii=False).encode("utf-8")
    headers = build_headers(cfg)
    if not stream:
        headers["Accept"] = "application/json"
    return urllib.request.Request(url, data=body, headers=headers, method="POST")


# ---------------------------------------------------------------------------
# SSE 解析
# ---------------------------------------------------------------------------

def parse_sse_line(line: str) -> tuple[str, str] | None:
    """解析一行 SSE。

    返回 ``("content", 文本)`` / ``("done", "")`` / ``None``（忽略注释、空行、未知行）。
    服务端在流中返回 error 时抛 :class:`ApiError`。
    """
    if line is None:
        return None
    line = line.strip("\r\n")
    if not line or line.startswith(":"):
        return None
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload:
        return None
    if payload == "[DONE]":
        return ("done", "")
    try:
        obj = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(obj, dict):
        err = obj.get("error")
        if err:
            msg = err.get("message") if isinstance(err, dict) else str(err)
            code = err.get("code") if isinstance(err, dict) else None
            kind = "http"
            if code in (401, 402, 429) or code in ("401", "402", "429"):
                kind = _kind_for_status(int(code))
            raise ApiError(kind, str(msg or "stream error"), status=code if isinstance(code, int) else None)
        choices = obj.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
            if isinstance(choice, dict):
                delta = choice.get("delta")
                if isinstance(delta, dict):
                    content = delta.get("content")
                    if content:
                        return ("content", str(content))
                message = choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if content:
                        return ("content", str(content))
    return None


class SSEDecoder:
    """增量 UTF-8 + 行缓冲的 SSE 解码器，可处理跨 chunk 的多字节字符。"""

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._buffer = ""

    def feed(self, chunk: bytes) -> list[tuple[str, str]]:
        events: list[tuple[str, str]] = []
        if not chunk:
            return events
        self._buffer += self._decoder.decode(chunk)
        while True:
            idx = self._buffer.find("\n")
            if idx < 0:
                break
            line = self._buffer[:idx]
            self._buffer = self._buffer[idx + 1 :]
            event = parse_sse_line(line)
            if event:
                events.append(event)
        return events

    def flush(self) -> list[tuple[str, str]]:
        events: list[tuple[str, str]] = []
        self._buffer += self._decoder.decode(b"", final=True)
        if self._buffer:
            event = parse_sse_line(self._buffer)
            if event:
                events.append(event)
        self._buffer = ""
        return events


# ---------------------------------------------------------------------------
# 错误映射
# ---------------------------------------------------------------------------

def _kind_for_status(status: int) -> str:
    if status == 401:
        return "auth"
    if status == 402:
        return "insufficient_balance"
    if status == 429:
        return "rate_limit"
    if 500 <= status <= 599:
        return "server"
    return "http"


def _map_exception(exc: BaseException) -> ApiError:
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, urllib.error.HTTPError):
        return ApiError(_kind_for_status(int(exc.code)), f"HTTP {exc.code}", status=int(exc.code))
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return ApiError("timeout", "连接超时")
        if isinstance(reason, ssl.SSLError):
            return ApiError("network", f"SSL 错误: {reason}")
        return ApiError("network", str(reason) or "网络错误")
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return ApiError("timeout", "请求超时")
    if isinstance(exc, ssl.SSLError):
        return ApiError("network", f"SSL 错误: {exc}")
    if isinstance(exc, OSError):
        return ApiError("network", str(exc))
    return ApiError("network", str(exc) or exc.__class__.__name__)


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read(4096)
        text = raw.decode("utf-8", errors="replace")
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                err = obj.get("error")
                if isinstance(err, dict):
                    return str(err.get("message") or text)[:300]
        except (json.JSONDecodeError, TypeError):
            pass
        return text[:300]
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------

class DeepSeekClient:
    def __init__(self, logger_: logging.Logger | None = None) -> None:
        self.log = logger_ or logger

    @staticmethod
    def has_key(cfg: dict[str, Any]) -> bool:
        return bool(effective_key(cfg))

    def stream_chat(
        self,
        cfg: dict[str, Any],
        messages: list[dict[str, str]],
        stop_event: Any = None,
    ) -> Iterator[str]:
        """流式请求，逐段 yield 文本增量。异常统一为 ApiError。"""
        api = cfg.get("api") or {}
        if not self.has_key(cfg):
            raise ApiError("no_key", "未配置 API Key")
        timeout = float(api.get("timeout") or 30)
        request = build_request(cfg, messages, stream=True)
        self.log.debug("POST %s model=%s messages=%d", request.full_url, api.get("model"), len(messages))
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except BaseException as exc:  # noqa: BLE001
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise _map_exception(exc) from exc
        decoder = SSEDecoder()
        try:
            with response:  # type: ignore[union-attr]
                while True:
                    if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
                        return
                    try:
                        # SSE 是行协议：readline 能即时返回已到达的行，
                        # 不依赖 Content-Length / chunked 或连接关闭（mock 服务端友好）
                        raw_line = response.readline()  # type: ignore[union-attr]
                    except BaseException as exc:  # noqa: BLE001
                        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                            raise
                        raise _map_exception(exc) from exc
                    if not raw_line:
                        for kind, text in decoder.flush():
                            if kind == "done":
                                return
                            yield text
                        return
                    for kind, text in decoder.feed(raw_line):
                        if kind == "done":
                            return
                        yield text
        finally:
            try:
                response.close()  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                pass

    def test_connection(self, cfg: dict[str, Any]) -> tuple[bool, str]:
        """设置窗口「测试连接」：非流式 minimal 请求。返回 (ok, 中文说明)。"""
        api = cfg.get("api") or {}
        if not self.has_key(cfg):
            return False, "未填写 API Key"
        timeout = min(20.0, float(api.get("timeout") or 30))
        messages = [
            {"role": "system", "content": "你是连接测试助手，只回复两个字：你好。"},
            {"role": "user", "content": "测试连接"},
        ]
        test_cfg = json.loads(json.dumps(cfg))
        test_cfg.setdefault("api", {})["max_tokens"] = 12
        request = build_request(test_cfg, messages, stream=False)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(65536)
            obj = json.loads(raw.decode("utf-8", errors="replace"))
            choices = obj.get("choices") or []
            content = ""
            if choices and isinstance(choices[0], dict):
                content = (choices[0].get("message") or {}).get("content") or ""
            model = api.get("model") or C.DEFAULT_MODEL
            reply = prompts.normalize_reply(str(content))[:30]
            if reply:
                return True, f"连接成功（{model}）：{reply}"
            return True, f"连接成功（{model}），但回复为空"
        except BaseException as exc:  # noqa: BLE001
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            error = _map_exception(exc)
            detail = prompts.ERROR_INFO.get(error.kind, ("", error.message))[1]
            return False, f"{detail}（{error.message}）"


# ---------------------------------------------------------------------------
# 会话上下文（最近 8 轮）
# ---------------------------------------------------------------------------

class ChatSession:
    def __init__(self, max_rounds: int = C.CONTEXT_ROUNDS) -> None:
        self.max_rounds = max(1, int(max_rounds))
        self._history: deque[dict[str, str]] = deque()

    def build_messages(self, cfg: dict[str, Any], user_text: str) -> list[dict[str, str]]:
        speech = cfg.get("speech") or {}
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": prompts.build_system_prompt(
                    speech.get("persona"), int(speech.get("max_chars") or C.DEFAULT_MAX_CHARS)
                ),
            }
        ]
        messages.extend(dict(item) for item in self._history)
        messages.append({"role": "user", "content": user_text})
        return messages

    def add_turn(self, user_text: str, reply: str) -> None:
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": reply})
        while len(self._history) > self.max_rounds * 2:
            self._history.popleft()

    def clear(self) -> None:
        self._history.clear()

    @property
    def rounds(self) -> int:
        return len(self._history) // 2

    @property
    def history(self) -> list[dict[str, str]]:
        return [dict(item) for item in self._history]


# 便捷函数（测试/外部脚本用）
def iter_sse_events(lines: Iterable[str]) -> Iterator[tuple[str, str]]:
    for line in lines:
        event = parse_sse_line(line)
        if event:
            yield event
