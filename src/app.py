"""桌宠应用控制器：把窗口/动画/气泡/聊天/托盘/设置/API 串起来。

线程模型：
- Tk 主线程：所有 UI 更新
- daemon 线程：API 流式请求、开关监听、托盘消息循环；结果统一投递 ``self._queue``，
  由 ``_pump``（after 80ms）在主线程消费
"""
from __future__ import annotations

import copy
import logging
import queue
import random
import threading
import time
import tkinter as tk
from tkinter import messagebox
from typing import Any

import anim
import api
import autostart
import bubble as bubble_module
import config as config_module
import constants as C
import platform_win
import prompts
import resources
import tray as tray_module

logger = logging.getLogger("bluewhale.app")


class PetApp:
    def __init__(
        self,
        root: tk.Tk,
        config: dict[str, Any],
        config_path: Any,
        logger_: logging.Logger | None = None,
        scale: float = 1.0,
        selftest: bool = False,
    ) -> None:
        self.root = root
        self.cfg = config
        self.config_path = config_path
        self.log = logger_ or logger
        self.scale = max(0.5, float(scale or 1.0))
        self.selftest = bool(selftest)
        self.data_dir = resources.data_dir()
        self.asset_root = resources.asset_root()
        self.app_root = resources.exe_dir()
        self.app_icon_path = resources.app_icon_path()

        self.manifest = anim.Manifest.load(resources.manifest_path())
        self.log.info(
            "资产清单已加载: %s 状态, %s 帧, 默认=%s",
            len(self.manifest.states),
            self.manifest.frame_total,
            self.manifest.default_state,
        )

        # 平台渲染模式 / XShape
        if platform_win.IS_WINDOWS:
            self.sprite_mode = "chroma"
            self.shaper = None
        else:
            import platform_linux

            self.shaper = platform_linux.XShape()
            self.sprite_mode = "shape" if self.shaper.available else "alpha"
            if not self.shaper.available:
                self.log.info("XShape 不可用，使用 -alpha 兜底: %s", self.shaper.reason)

        self.sprites = anim.SpriteCache(
            self.manifest,
            mode=self.sprite_mode,
            key_rgb=self.manifest.key_rgb,
            max_states=3,
            logger_=self.log,
        )
        self.pet = _pet_window_class()(
            root,
            config,
            self.manifest,
            callbacks=self,
            scale=self.scale,
            sprite_mode=self.sprite_mode,
            shaper=self.shaper,
        )
        self.sprites.set_render_size(self.pet.pixel_w, self.pet.pixel_h)

        self.animator = anim.Animator(
            self.manifest,
            schedule=self.root.after,
            on_frame=self._on_frame,
            fallback_state=self.manifest.default_state,
            logger_=self.log,
        )
        self._current_frame_name: str | None = None
        self._bob_toggle = False

        self.bubble = bubble_module.Bubble(
            root,
            pet_rect_provider=self.get_pet_rect,
            scale=self.scale,
            mode=self.sprite_mode,
            key_rgb=self.manifest.key_rgb,
            shaper=self.shaper,
            logger_=self.log,
        )

        self.session = api.ChatSession(C.CONTEXT_ROUNDS)
        self.client = api.DeepSeekClient(self.log)
        self.tray: tray_module.TrayManager | None = None

        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._chat_win: Any = None
        self._settings_win: Any = None

        self._closed = False
        self._started = False
        self.sleeping = False
        self.dragging = False
        self.streaming = False
        self._stream_thread: threading.Thread | None = None
        self._stream_stop = threading.Event()
        self._stream_text = ""
        self._stream_shown = ""
        self._last_user_text = ""
        self._last_interaction = time.monotonic()
        self._idle_after: str | None = None
        self._blink_after: str | None = None
        self._sleep_after: str | None = None
        self._pump_after: str | None = None
        self._persist_after: str | None = None
        self._refresh_after: str | None = None
        self._size_preview_after: str | None = None
        self._wave_after: str | None = None

        self.root.report_callback_exception = self._on_tk_exception

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self, show: bool = True) -> None:
        if self._started:
            return
        self._started = True
        self._play_state(self.manifest.default_state)
        if show:
            self.pet.show()
        self._pump_after = self._schedule(80, self._pump)
        self._schedule_blink()
        self._schedule_idle_action()
        self._schedule_sleep_check()
        if (self.cfg.get("system") or {}).get("tray", True):
            self._start_tray()
        if not self.selftest:
            self._schedule(500, self._greet)

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.log.info("应用正在退出")
        self.streaming = False
        self._stream_stop.set()
        if self._chat_win is not None:
            try:
                self._chat_win.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._chat_win = None
        if self._settings_win is not None:
            try:
                self._settings_win.close()
            except Exception:  # noqa: BLE001
                pass
            self._settings_win = None
        for attr in (
            "_idle_after",
            "_blink_after",
            "_sleep_after",
            "_pump_after",
            "_persist_after",
            "_refresh_after",
            "_size_preview_after",
            "_wave_after",
        ):
            after_id = getattr(self, attr, None)
            if after_id:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
                setattr(self, attr, None)
        try:
            self.bubble.destroy()
        except Exception:  # noqa: BLE001
            pass
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:  # noqa: BLE001
                pass
            self.tray = None
        try:
            self._sync_pet_state_to_config()
            config_module.save_config(self.config_path, self.cfg)
        except Exception:  # noqa: BLE001
            self.log.debug("退出保存配置失败", exc_info=True)
        try:
            self.pet.destroy()
        except Exception:  # noqa: BLE001
            pass
        if self.shaper is not None:
            try:
                self.shaper.close()
            except Exception:  # noqa: BLE001
                pass

    def quit_app(self) -> None:
        self.shutdown()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _on_tk_exception(self, exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
        self.log.error("Tk 回调异常", exc_info=(exc_type, exc_value, exc_tb))

    # ------------------------------------------------------------------
    # 动画帧
    # ------------------------------------------------------------------
    def _on_frame(self, state: str, frame_name: str, duration: int) -> None:
        entry = self.sprites.get(state, frame_name)
        if entry is not None:
            photo, mask = entry
            self.pet.set_frame(photo, mask)
            self._current_frame_name = frame_name
        self._bob_toggle = not self._bob_toggle
        if state in (self.manifest.default_state, "sleep"):
            bob = int(round(1 * self.scale)) if self._bob_toggle else 0
            self.pet.set_bob(bob)
        else:
            self.pet.set_bob(0)

    def _play_state(self, state: str, loop: bool | None = None, on_end: Any = None, force: bool = False) -> None:
        if self._closed and not force:
            return
        try:
            self.sprites.prepare(state)
            self.animator.play(state, loop=loop, on_end=on_end)
        except Exception:  # noqa: BLE001
            self.log.exception("播放表情失败 state=%s", state)

    def _on_state_end(self, state: str) -> bool:
        if self.sleeping:
            self._play_state("sleep", loop=True)
        else:
            self._play_state(self.manifest.default_state)
        return True

    def _return_to_idle(self, _state: str | None = None) -> bool:
        if self.sleeping:
            self._play_state("sleep", loop=True)
        else:
            self._play_state(self.manifest.default_state)
        return True

    # ------------------------------------------------------------------
    # 定时行为：眨眼 / 随机小动作 / 自动睡眠
    # ------------------------------------------------------------------
    def _schedule(self, delay_ms: int, callback: Any) -> str | None:
        try:
            return self.root.after(int(delay_ms), callback)
        except tk.TclError:
            return None

    def _schedule_blink(self) -> None:
        if self._closed:
            return
        self._blink_after = self._schedule(random.randint(2800, 6500), self._blink_tick)

    def _blink_tick(self) -> None:
        self._blink_after = None
        if self._closed:
            return
        behavior = self.cfg.get("behavior") or {}
        if (
            behavior.get("idle_animation", True)
            and not self.sleeping
            and not self.dragging
            and not self.streaming
            and self.animator.current_state == self.manifest.default_state
            and self.manifest.has_state("blink")
        ):
            self._play_state("blink", loop=False, on_end=self._on_state_end)
        self._schedule_blink()

    def _schedule_idle_action(self) -> None:
        if self._closed:
            return
        self._idle_after = self._schedule(random.randint(16000, 42000), self._idle_action_tick)

    def _idle_action_tick(self) -> None:
        self._idle_after = None
        if self._closed:
            return
        behavior = self.cfg.get("behavior") or {}
        candidates = [s for s in ("happy", "love", "wave", "eat", "think") if self.manifest.has_state(s)]
        if (
            behavior.get("idle_animation", True)
            and candidates
            and not self.sleeping
            and not self.dragging
            and not self.streaming
            and self.pet.visible
            and self.animator.current_state == self.manifest.default_state
        ):
            state = random.choice(candidates)
            if state == "wave":
                self._play_state(state, loop=False, on_end=self._on_state_end)
            else:
                self._play_state(state, loop=False, on_end=self._on_state_end)
        self._schedule_idle_action()

    def _schedule_sleep_check(self) -> None:
        if self._closed:
            return
        self._sleep_after = self._schedule(5000, self._sleep_check)

    def _sleep_check(self) -> None:
        self._sleep_after = None
        if self._closed:
            return
        behavior = self.cfg.get("behavior") or {}
        threshold = int(behavior.get("auto_sleep_seconds") or 0)
        if (
            threshold > 0
            and not self.sleeping
            and not self.streaming
            and not self.dragging
            and self.pet.visible
            and time.monotonic() - self._last_interaction >= threshold
            and self.animator.current_state in (self.manifest.default_state, "blink")
            and self.manifest.has_state("sleep")
        ):
            self._sleep()
        self._schedule_sleep_check()

    def _sleep(self) -> None:
        if self.sleeping:
            return
        self.sleeping = True
        self._play_state("sleep", loop=True)
        self.log.info("进入睡眠表情")

    def _wake(self) -> None:
        if not self.sleeping:
            return
        self.sleeping = False
        self.log.info("唤醒")
        if self.streaming:
            return
        if self.manifest.has_state("surprise"):
            self._play_state("surprise", loop=False, on_end=self._on_state_end)
        else:
            self._play_state(self.manifest.default_state)
        self.show_bubble(prompts.random_line("wake"))

    def mark_interaction(self) -> None:
        if self._closed:
            return
        self._last_interaction = time.monotonic()
        if self.sleeping and not self.selftest:
            self._wake()
        elif self.sleeping:
            self.sleeping = False
            self._play_state(self.manifest.default_state)

    # ------------------------------------------------------------------
    # 交互回调（PetWindow → App）
    # ------------------------------------------------------------------
    def on_poke(self) -> None:
        if self._closed:
            return
        behavior = self.cfg.get("behavior") or {}
        if not behavior.get("click_actions", True):
            return
        self.mark_interaction()
        if self.streaming or self.dragging:
            return
        line = prompts.random_line("poke")
        self.show_bubble(line)
        candidates = [s for s in ("happy", "laugh", "surprise", "love", "angry") if self.manifest.has_state(s)]
        if candidates:
            self._play_state(random.choice(candidates), loop=False, on_end=self._on_state_end)

    def on_double_click(self) -> None:
        if self._closed:
            return
        self.mark_interaction()
        self.open_chat()

    def on_context_menu(self, x: int, y: int) -> None:
        if self._closed:
            return
        self.mark_interaction()
        self._show_context_menu(x, y)

    def on_drag_start(self) -> None:
        if self._closed:
            return
        self.mark_interaction()
        self.dragging = True
        self.bubble.hide()
        if self.manifest.has_state("drag"):
            self._play_state("drag", loop=True)

    def on_drag_end(self) -> None:
        if self._closed:
            return
        self.dragging = False
        self._sync_pet_state_to_config()
        self._persist_soon()
        self._return_to_idle()
        if random.random() < 0.45:
            self.show_bubble(prompts.random_line("drag"))

    def on_wheel(self, direction: int) -> None:
        if self._closed:
            return
        behavior = self.cfg.get("behavior") or {}
        if not behavior.get("wheel_resize", True):
            return
        step = 8  # 逻辑像素步进，与屏幕 DPI 无关
        old = self.pet.logical_size
        new_size = old + direction * step
        if new_size < C.MIN_SIZE:
            new_size = C.MIN_SIZE
            self.show_bubble(prompts.random_line("resize"))
        elif new_size > C.MAX_SIZE:
            new_size = C.MAX_SIZE
            self.show_bubble(prompts.random_line("resize"))
        if new_size != old:
            self.pet.resize_logical(new_size)
            self.pet.logical_size = new_size
            pet_cfg = self.cfg.setdefault("pet", {})
            pet_cfg["size"] = new_size
            self._persist_soon()

    def on_size_changed(self, logical_size: int) -> None:
        """PetWindow 尺寸变化后重建当前表情帧。"""
        if self._closed:
            return
        self.sprites.set_render_size(self.pet.pixel_w, self.pet.pixel_h)
        pet_cfg = self.cfg.setdefault("pet", {})
        pet_cfg["size"] = int(logical_size)
        self._schedule_frame_refresh()
        self._persist_soon()

    def _schedule_frame_refresh(self) -> None:
        if self._refresh_after is not None:
            try:
                self.root.after_cancel(self._refresh_after)
            except tk.TclError:
                pass
        self._refresh_after = self._schedule(40, self._refresh_current_frame)

    def _refresh_current_frame(self) -> None:
        self._refresh_after = None
        if self._closed:
            return
        state = self.animator.current_state
        self.sprites.prepare(state)
        frame_name = self._current_frame_name
        if frame_name is None or frame_name not in self.manifest.frames(state):
            frames = self.manifest.frames(state)
            frame_name = frames[0] if frames else None
        if frame_name:
            entry = self.sprites.get(state, frame_name)
            if entry is not None:
                self.pet.set_frame(entry[0], entry[1])
                self._current_frame_name = frame_name

    # ------------------------------------------------------------------
    # 气泡
    # ------------------------------------------------------------------
    @property
    def pet_rect(self) -> tuple[int, int, int, int] | None:
        return self.get_pet_rect()

    def get_pet_rect(self) -> tuple[int, int, int, int] | None:
        try:
            x, y = self.pet.position()
            return x, y, self.pet.pixel_w, self.pet.pixel_h
        except Exception:  # noqa: BLE001
            return None

    def show_bubble(self, text: str, seconds: float | None = None, typewriter: bool | None = None) -> None:
        if self._closed:
            return
        speech = self.cfg.get("speech") or {}
        if seconds is None:
            seconds = int(speech.get("bubble_seconds") or C.DEFAULT_BUBBLE_SECONDS)
        if typewriter is None:
            typewriter = bool(speech.get("typewriter", True))
        text = prompts.truncate_text(prompts.normalize_reply(text), int(speech.get("max_chars") or C.DEFAULT_MAX_CHARS))
        if not text:
            return
        try:
            self.bubble.show(text, seconds=seconds, typewriter=typewriter)
        except Exception:  # noqa: BLE001
            self.log.exception("显示气泡失败")

    # ------------------------------------------------------------------
    # 聊天
    # ------------------------------------------------------------------
    def open_chat(self) -> None:
        if self._closed:
            return
        if self._chat_win is not None:
            self._chat_win.focus()
            return
        try:
            import chat as chat_module

            self._chat_win = chat_module.ChatWindow(
                self.root,
                self,
                scale=self.scale,
                pet_rect_provider=lambda: self.pet_rect,
                logger_=self.log,
            )
        except Exception:  # noqa: BLE001
            self.log.exception("打开聊天窗口失败")
            self._chat_win = None
            return
        if not self.client.has_key(self.cfg):
            try:
                self._chat_win.set_hint("未配置 API Key · 托盘→设置")
                self._chat_win.append_system(
                    "（未配置 API Key：托盘 → 设置 → API Key 填写后可接入 DeepSeek；现在先用内置短句陪你聊）"
                )
            except tk.TclError:
                pass

    def on_chat_closed(self) -> None:
        self._chat_win = None

    def demo_chat(self, text: str) -> None:
        """--demo-chat：打开聊天窗、填入文本并发送（走真实 API 路径，供 QA mock 验证）。"""
        text = (text or "").strip()
        if self._closed or not text:
            return
        self.open_chat()
        if self._chat_win is None:
            return
        try:
            self._chat_win.entry.delete("1.0", "end")
            self._chat_win.entry.insert("1.0", text)
        except tk.TclError:
            return
        self.root.after(250, self._demo_chat_send)

    def _demo_chat_send(self) -> None:
        if self._closed or self._chat_win is None:
            return
        try:
            self._chat_win.send()
        except Exception:  # noqa: BLE001
            self.log.exception("demo-chat 发送失败")

    def clear_context(self) -> None:
        self.session.clear()
        self.show_bubble("嗯，之前聊的我先忘掉啦～")

    def on_chat_send(self, text: str) -> None:
        if self._closed:
            return
        text = (text or "").strip()
        if not text:
            return
        self.mark_interaction()
        self._last_user_text = text
        if not self.client.has_key(self.cfg):
            self._local_chat_reply()
            return
        messages = self.session.build_messages(self.cfg, text)
        self.streaming = True
        self._stream_text = ""
        self._stream_shown = ""
        self._stream_stop = threading.Event()
        try:
            self.bubble.begin_stream("…")
        except Exception:  # noqa: BLE001
            self.log.debug("气泡开始流式失败", exc_info=True)
        if self.manifest.has_state("think"):
            self._play_state("think", loop=True)
        if self._chat_win is not None:
            try:
                self._chat_win.set_busy(True, "蓝鲸正在想…")
            except tk.TclError:
                pass
        self._stream_thread = threading.Thread(
            target=self._stream_worker,
            args=(copy.deepcopy(self.cfg), messages, self._stream_stop),
            name="BlueWhaleChatStream",
            daemon=True,
        )
        self._stream_thread.start()

    def _stream_worker(self, cfg: dict[str, Any], messages: list[dict[str, str]], stop_event: threading.Event) -> None:
        shown_any = False
        try:
            for delta in self.client.stream_chat(cfg, messages, stop_event):
                if stop_event.is_set():
                    return
                shown_any = True
                self._queue.put(("stream_delta", delta))
            self._queue.put(("stream_done", shown_any))
        except api.ApiError as exc:
            self.log.warning("聊天接口错误: kind=%s msg=%s", exc.kind, exc.message)
            self._queue.put(("stream_error", exc.kind))
        except Exception:  # noqa: BLE001
            self.log.exception("聊天请求异常")
            self._queue.put(("stream_error", "network"))

    def _on_stream_delta(self, delta: str) -> None:
        if not self.streaming or not delta:
            return
        if self.animator.current_state != "talk" and self.manifest.has_state("talk"):
            self._play_state("talk", loop=True)
            if self._chat_win is not None:
                try:
                    self._chat_win.set_status("蓝鲸正在说话…")
                except tk.TclError:
                    pass
        self._stream_text += delta
        speech = self.cfg.get("speech") or {}
        max_chars = int(speech.get("max_chars") or C.DEFAULT_MAX_CHARS)
        display = prompts.truncate_text(prompts.normalize_reply(self._stream_text), max_chars)
        if display and display != self._stream_shown:
            self._stream_shown = display
            try:
                self.bubble.replace_stream_text(display)
            except Exception:  # noqa: BLE001
                self.log.debug("流式气泡刷新失败", exc_info=True)

    def _on_stream_done(self, shown_any: Any) -> None:
        if not self.streaming:
            return
        self.streaming = False
        speech = self.cfg.get("speech") or {}
        max_chars = int(speech.get("max_chars") or C.DEFAULT_MAX_CHARS)
        final_text = prompts.clean_and_truncate(self._stream_text, max_chars)
        if not final_text:
            bubble_line, detail = prompts.error_reply("bad_response")
            self._finish_stream_error(bubble_line, detail)
            return
        self.session.add_turn(self._last_user_text, final_text)
        try:
            self.bubble.end_stream(final_text, seconds=int(speech.get("bubble_seconds") or C.DEFAULT_BUBBLE_SECONDS))
        except Exception:  # noqa: BLE001
            self.log.debug("结束流式气泡失败", exc_info=True)
        if self.manifest.has_state("happy"):
            self._play_state("happy", loop=False, on_end=self._on_state_end)
        else:
            self._return_to_idle()
        if self._chat_win is not None:
            try:
                self._chat_win.finish_reply(final_text)
            except tk.TclError:
                pass

    def _on_stream_error(self, kind: str) -> None:
        if not self.streaming:
            return
        self.streaming = False
        bubble_line, detail = prompts.error_reply(str(kind))
        self._finish_stream_error(bubble_line, detail)

    def _finish_stream_error(self, bubble_line: str, detail: str) -> None:
        self.log.info("聊天失败兜底: %s", detail)
        try:
            self.bubble.end_stream(
                prompts.truncate_text(bubble_line, int((self.cfg.get("speech") or {}).get("max_chars") or C.DEFAULT_MAX_CHARS)),
                seconds=int((self.cfg.get("speech") or {}).get("bubble_seconds") or C.DEFAULT_BUBBLE_SECONDS),
            )
        except Exception:  # noqa: BLE001
            pass
        if self.manifest.has_state("sad"):
            self._play_state("sad", loop=False, on_end=self._on_state_end)
        else:
            self._return_to_idle()
        if self._chat_win is not None:
            try:
                self._chat_win.finish_reply(bubble_line, error=True)
                self._chat_win.set_status(detail, error=True)
            except tk.TclError:
                pass

    def _local_chat_reply(self) -> None:
        """无 API Key：不请求网络，用内置短句兜底。"""
        line = prompts.clean_and_truncate(
            prompts.random_line("chat_no_key"),
            int((self.cfg.get("speech") or {}).get("max_chars") or C.DEFAULT_MAX_CHARS),
        )
        if self.manifest.has_state("talk"):
            self._play_state("talk", loop=True)
        self.show_bubble(line)
        if self.manifest.has_state("happy"):
            self._play_state("happy", loop=False, on_end=self._on_state_end)
        if self._chat_win is not None:
            try:
                self._chat_win.finish_reply(line)
                self._chat_win.set_hint("未配置 API Key · 托盘→设置")
            except tk.TclError:
                pass
        if (self.cfg.get("system") or {}).get("first_run", True):
            cfg = self.cfg.setdefault("system", {})
            cfg["first_run"] = False
            self._persist_soon()

    # ------------------------------------------------------------------
    # 托盘
    # ------------------------------------------------------------------
    def _start_tray(self) -> None:
        try:
            icon = resources.tray_icon_path()
            self.tray = tray_module.TrayManager(
                str(icon),
                on_action=self._on_tray_action,
                state_provider=self._tray_state,
                logger_=self.log,
            )
            if not self.tray.start():
                self.log.warning("托盘不可用，使用宠物右键菜单兜底")
        except Exception:  # noqa: BLE001
            self.log.exception("启动托盘异常")
            self.tray = None

    def _on_tray_action(self, action_id: int) -> None:
        # 可能来自托盘线程：只投递队列
        self._queue.put(("action", int(action_id)))

    def _tray_state(self) -> dict[str, Any]:
        pet_cfg = self.cfg.get("pet") or {}
        try:
            auto = autostart.is_enabled()
        except Exception:  # noqa: BLE001
            auto = bool((self.cfg.get("system") or {}).get("autostart"))
        return {
            "visible": self.pet.visible,
            "always_on_top": bool(pet_cfg.get("always_on_top", True)),
            "click_through": bool(pet_cfg.get("click_through", False)),
            "autostart": auto,
            "size": self.pet.logical_size,
        }

    # ------------------------------------------------------------------
    # 队列泵
    # ------------------------------------------------------------------
    def _pump(self) -> None:
        self._pump_after = None
        if self._closed:
            return
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                try:
                    if kind == "action":
                        self._handle_action(int(payload))
                    elif kind == "wake":
                        self._on_wake_request()
                    elif kind == "stream_delta":
                        self._on_stream_delta(str(payload))
                    elif kind == "stream_done":
                        self._on_stream_done(payload)
                    elif kind == "stream_error":
                        self._on_stream_error(str(payload))
                except Exception:  # noqa: BLE001
                    self.log.exception("处理队列消息失败 kind=%s", kind)
        except queue.Empty:
            pass
        if not self._closed:
            self._pump_after = self._schedule(80, self._pump)

    def _on_wake_request(self) -> None:
        """第二个实例启动时唤醒本实例。"""
        if self._closed:
            return
        self.pet.show(focus=True)
        self.mark_interaction()
        self.show_bubble(prompts.random_line("show"))
        self.log.info("被二次启动唤醒")

    # ------------------------------------------------------------------
    # 动作分发
    # ------------------------------------------------------------------
    def _handle_action(self, action_id: int) -> None:
        if action_id == C.Action.CHAT:
            self.open_chat()
        elif action_id == C.Action.SETTINGS:
            self.open_settings()
        elif action_id == C.Action.TOGGLE_SHOW:
            self.toggle_show()
        elif action_id == C.Action.TOGGLE_TOP:
            self.toggle_topmost()
        elif action_id == C.Action.TOGGLE_AUTOSTART:
            self.toggle_autostart()
        elif action_id == C.Action.TOGGLE_CLICK_THROUGH:
            self.toggle_click_through()
        elif action_id == C.Action.ABOUT:
            self.show_about()
        elif action_id == C.Action.QUIT:
            self.quit_app()
        elif action_id in tuple(value for _label, value in C.SIZE_PRESETS):
            self.set_size(int(action_id))
        elif action_id == C.Action.SIZE_DEFAULT:
            self.set_size(C.DEFAULT_SIZE)
        else:
            self.log.debug("未知动作 id=%s", action_id)

    def toggle_show(self) -> None:
        visible = self.pet.toggle()
        if visible:
            self.mark_interaction()
            self.show_bubble(prompts.random_line("show"))

    def set_size(self, size: int) -> None:
        self.pet.resize_logical(int(size))
        self.cfg.setdefault("pet", {})["size"] = self.pet.logical_size
        self._persist_soon()

    def toggle_topmost(self) -> None:
        pet_cfg = self.cfg.setdefault("pet", {})
        new_value = not bool(pet_cfg.get("always_on_top", True))
        pet_cfg["always_on_top"] = new_value
        self.pet.set_always_on_top(new_value)
        self._persist_soon()
        if self._settings_win is not None:
            try:
                self._settings_win.var_topmost.set(new_value)
            except tk.TclError:
                pass

    def toggle_click_through(self) -> None:
        pet_cfg = self.cfg.setdefault("pet", {})
        new_value = not bool(pet_cfg.get("click_through", False))
        pet_cfg["click_through"] = new_value
        self.pet.set_click_through(new_value)
        self._persist_soon()
        if new_value:
            self.show_bubble("鼠标穿透已开启：右键托盘菜单可关闭，设置窗口也不受影响～")
        if self._settings_win is not None:
            try:
                self._settings_win.var_click_through.set(new_value)
            except tk.TclError:
                pass

    def toggle_autostart(self) -> None:
        desired = not autostart.is_enabled()
        ok, message = autostart.set_enabled(desired)
        if ok:
            self.cfg.setdefault("system", {})["autostart"] = desired
            self._persist_soon()
            self.show_bubble("开机自启：" + ("已开启" if desired else "已关闭"))
        else:
            self.show_bubble(message)
        if self._settings_win is not None:
            try:
                self._settings_win.var_autostart.set(autostart.is_enabled())
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Tk 右键菜单
    # ------------------------------------------------------------------
    def _show_context_menu(self, x: int, y: int) -> None:
        pet_cfg = self.cfg.get("pet") or {}
        system_cfg = self.cfg.get("system") or {}
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="和蓝鲸聊聊", command=self.open_chat)
        menu.add_command(label="设置…", command=self.open_settings)
        menu.add_separator()
        menu.add_command(label="隐藏桌宠" if self.pet.visible else "显示桌宠", command=self.toggle_show)
        size_menu = tk.Menu(menu, tearoff=0)
        for label, value in C.SIZE_PRESETS:
            size_menu.add_command(label=f"{label}（{value}px）", command=lambda v=value: self.set_size(v))
        size_menu.add_separator()
        size_menu.add_command(label="恢复默认尺寸", command=lambda: self.set_size(C.DEFAULT_SIZE))
        menu.add_cascade(label="大小", menu=size_menu)
        menu.add_separator()
        topmost_var = tk.BooleanVar(value=bool(pet_cfg.get("always_on_top", True)))
        menu.add_checkbutton(label="窗口置顶", variable=topmost_var, command=self.toggle_topmost)
        click_var = tk.BooleanVar(value=bool(pet_cfg.get("click_through", False)))
        menu.add_checkbutton(label="鼠标穿透", variable=click_var, command=self.toggle_click_through)
        autostart_var = tk.BooleanVar(value=autostart.is_enabled())
        menu.add_checkbutton(label="开机自启", variable=autostart_var, command=self.toggle_autostart)
        menu.add_separator()
        menu.add_command(label="关于蓝色大肥鱼", command=self.show_about)
        menu.add_command(label="退出", command=self.quit_app)
        try:
            menu.tk_popup(int(x), int(y))
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # 设置窗口
    # ------------------------------------------------------------------
    def open_settings(self) -> None:
        if self._closed:
            return
        if self._settings_win is not None:
            self._settings_win.focus()
            return
        if self._chat_win is not None:
            try:
                self._chat_win.set_topmost(False)
            except Exception:  # noqa: BLE001
                pass
        try:
            import settings_window

            self._settings_win = settings_window.SettingsWindow(
                self.root, self, scale=self.scale, logger_=self.log
            )
        except Exception:  # noqa: BLE001
            self.log.exception("打开设置窗口失败")
            self._settings_win = None
            self.show_bubble("设置窗口打开失败，请查看日志 QAQ")

    def on_settings_closed(self) -> None:
        self._settings_win = None
        if self._chat_win is not None:
            try:
                self._chat_win.set_topmost(True)
            except Exception:  # noqa: BLE001
                pass

    def open_settings_autoclose(self, close_after_ms: int = 8000) -> None:
        """--open-settings：打开设置窗口，若仍未被关闭则到时自动关闭（供截图脚本退出）。"""
        self.open_settings()
        if self._settings_win is not None and close_after_ms > 0:
            self.root.after(int(close_after_ms), self._autoclose_settings)

    def _autoclose_settings(self) -> None:
        if self._closed or self._settings_win is None:
            return
        try:
            self._settings_win.close()
        except Exception:  # noqa: BLE001
            self.log.debug("自动关闭设置窗口失败", exc_info=True)

    def get_config(self) -> dict[str, Any]:
        self._sync_pet_state_to_config()
        return copy.deepcopy(self.cfg)

    def get_default_config(self) -> dict[str, Any]:
        return config_module.default_config()

    def preview_settings(self, cfg: dict[str, Any]) -> None:
        """外观即时预览（不落盘）。"""
        if self._closed:
            return
        pet_cfg = cfg.get("pet") or {}
        try:
            size = int(pet_cfg.get("size") or self.pet.logical_size)
        except (TypeError, ValueError):
            size = self.pet.logical_size
        if size != self.pet.logical_size:
            if self._size_preview_after is not None:
                try:
                    self.root.after_cancel(self._size_preview_after)
                except tk.TclError:
                    pass
            self._size_preview_after = self._schedule(
                70, lambda: self._apply_preview_size(int(size))
            )
        self.pet.set_opacity(float(pet_cfg.get("opacity", 1.0) or 1.0))
        self.pet.set_always_on_top(bool(pet_cfg.get("always_on_top", True)))
        current_click = bool((self.cfg.get("pet") or {}).get("click_through"))
        desired_click = bool(pet_cfg.get("click_through", False))
        if desired_click != current_click:
            self.pet.set_click_through(desired_click)

    def _apply_preview_size(self, size: int) -> None:
        self._size_preview_after = None
        if self._closed:
            return
        self.pet.resize_logical(size)

    def apply_settings(self, cfg: dict[str, Any], persist: bool = True) -> tuple[bool, str]:
        warnings: list[str] = []
        try:
            new_cfg, warnings = config_module.normalize_config(cfg)
        except Exception:  # noqa: BLE001
            self.log.exception("规范化设置失败")
            return False, "设置格式不合法"
        if persist:
            desired_autostart = bool((new_cfg.get("system") or {}).get("autostart", False))
            if desired_autostart != autostart.is_enabled():
                ok, message = autostart.set_enabled(desired_autostart)
                if not ok:
                    warnings.append(message)
        self.cfg = new_cfg
        self._apply_current_config()
        if persist:
            config_module.save_config(self.config_path, self.cfg)
        message = "；".join(warnings) if warnings else ""
        return True, message

    def restore_settings(self, cfg: dict[str, Any]) -> None:
        try:
            new_cfg, _warnings = config_module.normalize_config(cfg)
        except Exception:  # noqa: BLE001
            return
        self.cfg = new_cfg
        self._apply_current_config()

    def _apply_current_config(self) -> None:
        pet_cfg = self.cfg.get("pet") or {}
        try:
            size = int(pet_cfg.get("size") or self.pet.logical_size)
        except (TypeError, ValueError):
            size = self.pet.logical_size
        if size != self.pet.logical_size:
            self.pet.resize_logical(size)
        self.pet.set_opacity(float(pet_cfg.get("opacity", 1.0) or 1.0))
        self.pet.set_always_on_top(bool(pet_cfg.get("always_on_top", True)))
        self.pet.set_click_through(bool(pet_cfg.get("click_through", False)))
        if not self.streaming:
            self._return_to_idle()

    def show_about(self) -> None:
        text = (
            f"{C.APP_NAME} {C.APP_VERSION}\n{C.APP_SUBTITLE}\n\n"
            f"资产目录：{self.asset_root}\n"
            f"数据目录：{self.data_dir}\n"
            f"配置文件：{self.config_path}\n\n"
            "基于 DeepSeek API 的桌面宠物；蓝鲸美术为非官方二创，仅供个人使用。\n"
            "代码许可：MIT"
        )
        try:
            messagebox.showinfo("关于蓝色大肥鱼", text, parent=self.pet.win if self.pet else None)
        except Exception:  # noqa: BLE001
            self.log.debug("显示关于窗口失败", exc_info=True)

    # ------------------------------------------------------------------
    # 启动问候 / 持久化
    # ------------------------------------------------------------------
    def _greet(self) -> None:
        if self._closed or self.selftest:
            return
        system_cfg = self.cfg.get("system") or {}
        behavior = self.cfg.get("behavior") or {}
        if system_cfg.get("first_run", True):
            self.show_bubble(prompts.random_line("first_run"))
            self.cfg.setdefault("system", {})["first_run"] = False
            self._persist_soon()
        elif behavior.get("greet_on_start", True):
            self.show_bubble(prompts.random_line("greet"))
        if self.manifest.has_state("wave"):
            self._play_state("wave", loop=True)
            self._wave_after = self._schedule(2600, self._end_wave)
        elif self.manifest.has_state("happy"):
            self._play_state("happy", loop=False, on_end=self._on_state_end)

    def _end_wave(self) -> None:
        self._wave_after = None
        if self._closed:
            return
        if self.animator.current_state == "wave":
            self._return_to_idle()

    def _sync_pet_state_to_config(self) -> None:
        pet_cfg = self.cfg.setdefault("pet", {})
        try:
            pet_cfg["size"] = int(self.pet.logical_size)
            x, y = self.pet.logical_position()
            pet_cfg["x"] = int(x)
            pet_cfg["y"] = int(y)
        except Exception:  # noqa: BLE001
            self.log.debug("同步窗口状态失败", exc_info=True)

    def _persist_soon(self, delay_ms: int = 700) -> None:
        if self._closed:
            return
        if self._persist_after is not None:
            try:
                self.root.after_cancel(self._persist_after)
            except tk.TclError:
                pass
        self._persist_after = self._schedule(delay_ms, self._persist_now)

    def _persist_now(self) -> None:
        self._persist_after = None
        if self._closed:
            return
        self._sync_pet_state_to_config()
        try:
            config_module.save_config(self.config_path, self.cfg)
        except Exception:  # noqa: BLE001
            self.log.exception("保存配置异常")


def _pet_window_class() -> Any:
    from pet_window import PetWindow

    return PetWindow
