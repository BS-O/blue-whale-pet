"""设置窗口（SPEC §6、任务板 task-2）。

标签页：API / 外观 / 互动 / 人设；底部：保存 / 取消 / 恢复默认 / 打开数据目录 / 关于。
外观类设置拖动即时预览，保存后落盘并生效；API Key 掩码显示、可点「显示」。
"""
from __future__ import annotations

import copy
import logging
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk
from typing import Any

import api
import autostart
import config as config_module
import constants as C
import platform_win
from chat import pick_font_family

logger = logging.getLogger("bluewhale.settings")


class SettingsWindow:
    def __init__(self, root: tk.Tk, app: Any, scale: float = 1.0, logger_: logging.Logger | None = None) -> None:
        self.root = root
        self.app = app
        self.scale = max(0.5, float(scale or 1.0))
        self.log = logger_ or logger
        self._loading = True
        self._closed = False
        self._test_queue: queue.Queue[tuple[bool, str]] = queue.Queue()
        self._test_poll: str | None = None
        self._family = pick_font_family(root)
        self.original_config = copy.deepcopy(app.get_config())

        width = int(round(520 * self.scale))
        height = int(round(600 * self.scale))
        self.win = tk.Toplevel(root, class_=C.WM_CLASS)
        self.win.title("设置 - 蓝色大肥鱼")
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        try:
            icon = app.app_icon_path
            if icon and icon.is_file():
                self.win.iconbitmap(str(icon))
        except (tk.TclError, OSError, AttributeError):
            pass

        self._create_vars()
        outer = ttk.Frame(self.win, padding=int(round(10 * self.scale)))
        outer.pack(fill="both", expand=True)
        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)
        self._build_api_tab()
        self._build_appearance_tab()
        self._build_behavior_tab()
        self._build_persona_tab()
        self._build_buttons(outer)
        self._load_config(self.original_config)
        self._place(width, height)
        self._loading = False
        self.win.deiconify()
        self.win.lift()
        try:
            self.win.focus_force()
        except tk.TclError:
            pass
        # 顶层窗口焦点变化可能被聊天窗口抢到，稍后再抬一次保证设置窗口可见
        try:
            self.win.after(120, lambda: self._raise_self())
        except tk.TclError:
            pass
        try:
            platform_win.set_window_title(self.win, "设置 - 蓝色大肥鱼")
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # 变量
    # ------------------------------------------------------------------
    def _raise_self(self) -> None:
        if self._closed:
            return
        try:
            self.win.lift()
            self.win.focus_force()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    def _create_vars(self) -> None:
        self.var_api_key = tk.StringVar()
        self.var_show_key = tk.BooleanVar(value=False)
        self.var_provider = tk.StringVar()
        self._provider_keys: dict[str, str] = {}
        self._current_provider: str = C.DEFAULT_PROVIDER
        self.var_model = tk.StringVar()
        self.var_base_url = tk.StringVar()
        self.var_timeout = tk.IntVar(value=30)
        self.var_max_tokens = tk.IntVar(value=120)
        self.var_temperature = tk.DoubleVar(value=1.3)

        self.var_size = tk.IntVar(value=C.DEFAULT_SIZE)
        self.var_opacity = tk.IntVar(value=100)
        self.var_topmost = tk.BooleanVar(value=True)
        self.var_click_through = tk.BooleanVar(value=False)

        self.var_autostart = tk.BooleanVar(value=False)
        self.var_auto_sleep = tk.IntVar(value=C.DEFAULT_AUTO_SLEEP_SECONDS)
        self.var_bubble_seconds = tk.IntVar(value=C.DEFAULT_BUBBLE_SECONDS)
        self.var_typewriter = tk.BooleanVar(value=True)
        self.var_idle_animation = tk.BooleanVar(value=True)
        self.var_greet = tk.BooleanVar(value=True)
        self.var_wheel_resize = tk.BooleanVar(value=True)
        self.var_click_actions = tk.BooleanVar(value=True)
        self.var_tray = tk.BooleanVar(value=True)

        self.var_persona = tk.StringVar()
        self.var_max_chars = tk.IntVar(value=C.DEFAULT_MAX_CHARS)

        self.var_size_label = tk.StringVar(value="")
        self.var_opacity_label = tk.StringVar(value="")
        self.var_model_hint = tk.StringVar(value="默认 deepseek-flash（快、便宜）；也可输入自定义模型名")
        self.var_test_status = tk.StringVar(value="")
        self.var_test_color = tk.StringVar(value="#66708A")
        self.var_status = tk.StringVar(value="")

    # ------------------------------------------------------------------
    # 标签页构建
    # ------------------------------------------------------------------
    def _new_tab(self, title: str) -> tuple[ttk.Frame, int]:
        frame = ttk.Frame(self.notebook, padding=int(round(12 * self.scale)))
        self.notebook.add(frame, text=title)
        frame.columnconfigure(1, weight=1)
        return frame, 0

    def _label(self, parent: ttk.Frame, text: str, row: int) -> ttk.Label:
        label = ttk.Label(parent, text=text)
        label.grid(row=row, column=0, sticky="w", pady=int(round(4 * self.scale)), padx=(0, int(round(8 * self.scale))))
        return label

    def _entry(self, parent: ttk.Frame, row: int, textvariable: tk.Variable, width: int = 32, show: str | None = None) -> ttk.Entry:
        entry = ttk.Entry(parent, textvariable=textvariable, width=width)
        if show:
            entry.configure(show=show)
        entry.grid(row=row, column=1, sticky="ew", pady=int(round(3 * self.scale)))
        return entry

    def _build_api_tab(self) -> None:
        frame, row = self._new_tab("API")
        self._label(frame, "平台", row)
        provider_combo = ttk.Combobox(
            frame,
            textvariable=self.var_provider,
            values=list(C.PROVIDER_LABELS),
            width=30,
            state="readonly",
        )
        provider_combo.grid(row=row, column=1, sticky="ew", pady=int(round(3 * self.scale)))
        provider_combo.bind("<<ComboboxSelected>>", self._on_provider_selected)
        row += 1
        self._label(frame, "API Key", row)
        key_row = ttk.Frame(frame)
        key_row.grid(row=row, column=1, sticky="ew", pady=int(round(3 * self.scale)))
        key_row.columnconfigure(0, weight=1)
        self.entry_key = ttk.Entry(key_row, textvariable=self.var_api_key, width=34, show="*")
        self.entry_key.grid(row=0, column=0, sticky="ew")
        ttk.Checkbutton(key_row, text="显示", variable=self.var_show_key, command=self._toggle_key_visible).grid(
            row=0, column=1, padx=(int(round(6 * self.scale)), 0)
        )
        row += 1
        hint = ttk.Label(
            frame,
            text="仅保存在本机数据目录，不会上传；无 Key 时可用内置短句互动。",
            foreground="#66708A",
        )
        hint.grid(row=row, column=1, sticky="w", pady=(0, int(round(6 * self.scale))))
        row += 1
        self._label(frame, "模型", row)
        self.model_combo = ttk.Combobox(
            frame,
            textvariable=self.var_model,
            values=self._model_choices(),
            width=30,
        )
        self.model_combo.grid(row=row, column=1, sticky="ew", pady=int(round(3 * self.scale)))
        row += 1
        ttk.Label(frame, textvariable=self.var_model_hint, foreground="#66708A").grid(
            row=row, column=1, sticky="w", pady=(0, int(round(6 * self.scale)))
        )
        row += 1
        self._label(frame, "Base URL", row)
        self._entry(frame, row, self.var_base_url)
        row += 1
        self._label(frame, "超时（秒）", row)
        ttk.Spinbox(frame, from_=5, to=120, textvariable=self.var_timeout, width=8).grid(
            row=row, column=1, sticky="w", pady=int(round(3 * self.scale))
        )
        row += 1
        self._label(frame, "max_tokens", row)
        ttk.Spinbox(frame, from_=16, to=2048, increment=8, textvariable=self.var_max_tokens, width=8).grid(
            row=row, column=1, sticky="w", pady=int(round(3 * self.scale))
        )
        row += 1
        self._label(frame, "temperature", row)
        ttk.Spinbox(
            frame, from_=0.0, to=2.0, increment=0.1, textvariable=self.var_temperature, width=8
        ).grid(row=row, column=1, sticky="w", pady=int(round(3 * self.scale)))
        row += 1
        test_row = ttk.Frame(frame)
        test_row.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(int(round(10 * self.scale)), 0))
        self.test_button = ttk.Button(test_row, text="测试连接", command=self._test_connection)
        self.test_button.pack(side="left")
        ttk.Label(test_row, textvariable=self.var_test_status, foreground="#66708A").pack(
            side="left", padx=(int(round(8 * self.scale)), 0)
        )
        # 状态颜色用 label 动态前景
        self.test_label = test_row.winfo_children()[-1]
        self.var_test_color.trace_add("write", lambda *_a: self._apply_test_color())

    def _build_appearance_tab(self) -> None:
        frame, row = self._new_tab("外观")
        self._label(frame, "桌宠大小", row)
        size_box = ttk.Frame(frame)
        size_box.grid(row=row, column=1, sticky="ew", pady=int(round(3 * self.scale)))
        size_box.columnconfigure(0, weight=1)
        ttk.Scale(
            size_box,
            from_=C.MIN_SIZE,
            to=C.MAX_SIZE,
            variable=self.var_size,
            command=self._on_size_scale,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(size_box, textvariable=self.var_size_label, width=12).grid(row=0, column=1, padx=(int(round(6 * self.scale)), 0))
        row += 1
        self._label(frame, "不透明度", row)
        opacity_box = ttk.Frame(frame)
        opacity_box.grid(row=row, column=1, sticky="ew", pady=int(round(3 * self.scale)))
        opacity_box.columnconfigure(0, weight=1)
        ttk.Scale(
            opacity_box, from_=30, to=100, variable=self.var_opacity, command=self._on_opacity_scale
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(opacity_box, textvariable=self.var_opacity_label, width=12).grid(
            row=0, column=1, padx=(int(round(6 * self.scale)), 0)
        )
        row += 1
        ttk.Checkbutton(frame, text="窗口置顶", variable=self.var_topmost, command=self._preview_visual).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=int(round(4 * self.scale))
        )
        row += 1
        ttk.Checkbutton(
            frame, text="鼠标穿透（开启后只能通过托盘操作）", variable=self.var_click_through, command=self._preview_visual
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=int(round(4 * self.scale)))
        row += 1
        ttk.Checkbutton(frame, text="滚轮缩放", variable=self.var_wheel_resize).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=int(round(4 * self.scale))
        )
        row += 1
        ttk.Separator(frame, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky="ew", pady=int(round(8 * self.scale)))
        row += 1
        ttk.Label(
            frame,
            text="提示：右键拖动宠物可移动位置；滚轮可快速缩放；位置/大小会自动保存。",
            foreground="#66708A",
            wraplength=int(round(400 * self.scale)),
        ).grid(row=row, column=0, columnspan=2, sticky="w")

    def _build_behavior_tab(self) -> None:
        frame, row = self._new_tab("互动")
        self._label(frame, "气泡显示（秒）", row)
        ttk.Spinbox(frame, from_=1, to=60, textvariable=self.var_bubble_seconds, width=8).grid(
            row=row, column=1, sticky="w", pady=int(round(3 * self.scale))
        )
        row += 1
        self._label(frame, "自动睡眠（秒）", row)
        ttk.Spinbox(frame, from_=0, to=7200, increment=10, textvariable=self.var_auto_sleep, width=8).grid(
            row=row, column=1, sticky="w", pady=int(round(3 * self.scale))
        )
        row += 1
        ttk.Label(frame, text="0 = 不自动睡眠", foreground="#66708A").grid(
            row=row, column=1, sticky="w", pady=(0, int(round(4 * self.scale)))
        )
        row += 1
        checks = (
            ("打字机气泡效果", self.var_typewriter),
            ("待机动画 + 随机眨眼", self.var_idle_animation),
            ("启动时打招呼", self.var_greet),
            ("左键戳一戳有反应", self.var_click_actions),
            ("启用系统托盘（重启生效）", self.var_tray),
            ("开机自动启动", self.var_autostart),
        )
        for text, var in checks:
            ttk.Checkbutton(frame, text=text, variable=var).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=int(round(3 * self.scale))
            )
            row += 1
        if not autostart.is_supported():
            ttk.Label(frame, text="当前平台不支持开机自启", foreground="#B45309").grid(
                row=row, column=0, columnspan=2, sticky="w", pady=int(round(4 * self.scale))
            )

    def _build_persona_tab(self) -> None:
        frame, row = self._new_tab("人设")
        ttk.Label(frame, text="人设（会写入系统提示词）", font=(self._family, 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, int(round(4 * self.scale)))
        )
        row += 1
        self.persona_text = tk.Text(
            frame,
            height=9,
            wrap="word",
            font=(self._family, 10),
            relief="solid",
            borderwidth=1,
            padx=int(round(6 * self.scale)),
            pady=int(round(4 * self.scale)),
        )
        self.persona_text.grid(row=row, column=0, columnspan=2, sticky="nsew")
        frame.rowconfigure(row, weight=1)
        row += 1
        self._label(frame, "回复字数上限", row)
        ttk.Spinbox(frame, from_=10, to=200, increment=5, textvariable=self.var_max_chars, width=8).grid(
            row=row, column=1, sticky="w", pady=int(round(6 * self.scale))
        )
        row += 1
        ttk.Label(
            frame,
            text="默认要求：1~2 句、≤60 字、可用语气词/颜文字；留空则使用内置人设。",
            foreground="#66708A",
            wraplength=int(round(400 * self.scale)),
        ).grid(row=row, column=0, columnspan=2, sticky="w")

    def _build_buttons(self, outer: ttk.Frame) -> None:
        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(int(round(8 * self.scale)), 0))
        ttk.Button(row, text="保存", command=self.save).pack(side="right", padx=int(round(3 * self.scale)))
        ttk.Button(row, text="取消", command=self.cancel).pack(side="right", padx=int(round(3 * self.scale)))
        ttk.Button(row, text="恢复默认", command=self.restore_defaults).pack(side="left", padx=int(round(3 * self.scale)))
        ttk.Button(row, text="打开数据目录", command=self.open_data_dir).pack(side="left", padx=int(round(3 * self.scale)))
        ttk.Button(row, text="关于", command=self.about).pack(side="left", padx=int(round(3 * self.scale)))
        ttk.Label(row, textvariable=self.var_status, foreground="#B42318").pack(side="right", padx=int(round(8 * self.scale)))

    # ------------------------------------------------------------------
    # 数据装载 / 收集
    # ------------------------------------------------------------------
    def _load_config(self, cfg: dict[str, Any]) -> None:
        self._loading = True
        try:
            api_cfg = cfg.get("api") or {}
            pet = cfg.get("pet") or {}
            speech = cfg.get("speech") or {}
            behavior = cfg.get("behavior") or {}
            system = cfg.get("system") or {}
            self._provider_keys = {
                pid: str((api_cfg.get("keys") or {}).get(pid) or "") for pid in C.PROVIDERS
            }
            legacy = str(api_cfg.get("key") or "")
            provider = str(api_cfg.get("provider") or C.DEFAULT_PROVIDER).lower()
            if provider not in C.PROVIDERS:
                provider = C.DEFAULT_PROVIDER
            if not self._provider_keys.get(provider) and legacy and provider == C.DEFAULT_PROVIDER:
                self._provider_keys[C.DEFAULT_PROVIDER] = legacy
            self._current_provider = provider
            self.var_provider.set(C.PROVIDERS[provider]["label"])
            self.var_api_key.set(self._provider_keys.get(provider, ""))
            self.model_combo.configure(values=self._model_choices())
            preset = C.PROVIDERS[provider]
            self.var_model_hint.set(f"默认 {preset['default_model']}；也可输入 {preset['label']} 自定义模型名")
            self.var_model.set(str(api_cfg.get("model") or preset["default_model"]))
            self.var_base_url.set(str(api_cfg.get("base_url") or preset["base_url"]))
            self.var_timeout.set(int(api_cfg.get("timeout") or 30))
            self.var_max_tokens.set(int(api_cfg.get("max_tokens") or 120))
            self.var_temperature.set(float(api_cfg.get("temperature", 1.3) or 1.3))
            self.var_size.set(int(pet.get("size") or C.DEFAULT_SIZE))
            self.var_opacity.set(int(round(float(pet.get("opacity", 1.0) or 1.0) * 100)))
            self.var_topmost.set(bool(pet.get("always_on_top", True)))
            self.var_click_through.set(bool(pet.get("click_through", False)))
            self.var_autostart.set(bool(system.get("autostart", False)))
            self.var_tray.set(bool(system.get("tray", True)))
            self.var_auto_sleep.set(int(behavior.get("auto_sleep_seconds", C.DEFAULT_AUTO_SLEEP_SECONDS)))
            self.var_typewriter.set(bool(speech.get("typewriter", True)))
            self.var_idle_animation.set(bool(behavior.get("idle_animation", True)))
            self.var_greet.set(bool(behavior.get("greet_on_start", True)))
            self.var_wheel_resize.set(bool(behavior.get("wheel_resize", True)))
            self.var_click_actions.set(bool(behavior.get("click_actions", True)))
            self.var_bubble_seconds.set(int(speech.get("bubble_seconds", C.DEFAULT_BUBBLE_SECONDS)))
            self.var_max_chars.set(int(speech.get("max_chars", C.DEFAULT_MAX_CHARS)))
            persona = str(speech.get("persona") or "")
            if persona.strip() == "" or persona == self._persona_placeholder():
                persona = ""
            self.var_persona.set(persona)
            self._set_persona_text(persona)
            self._refresh_labels()
        finally:
            self._loading = False

    @staticmethod
    def _persona_placeholder() -> str:
        import prompts

        return prompts.PERSONA_PLACEHOLDER

    def _set_persona_text(self, text: str) -> None:
        try:
            self.persona_text.delete("1.0", "end")
            if text.strip():
                self.persona_text.insert("1.0", text)
        except tk.TclError:
            pass

    def _persona_value(self) -> str:
        try:
            return self.persona_text.get("1.0", "end").strip()
        except tk.TclError:
            return ""

    def _collect_config(self) -> dict[str, Any]:
        cfg = copy.deepcopy(self.original_config)
        provider = self._current_provider
        self._provider_keys[provider] = self.var_api_key.get().strip()
        cfg.setdefault("api", {}).update(
            {
                "provider": provider,
                "keys": dict(self._provider_keys),
                "key": self._provider_keys.get(C.DEFAULT_PROVIDER, ""),
                "model": self.var_model.get().strip() or C.DEFAULT_MODEL,
                "base_url": self.var_base_url.get().strip() or C.DEFAULT_BASE_URL,
                "timeout": int(self.var_timeout.get()),
                "max_tokens": int(self.var_max_tokens.get()),
                "temperature": float(self.var_temperature.get()),
            }
        )
        cfg.setdefault("pet", {}).update(
            {
                "size": int(self.var_size.get()),
                "always_on_top": bool(self.var_topmost.get()),
                "opacity": round(int(self.var_opacity.get()) / 100.0, 3),
                "click_through": bool(self.var_click_through.get()),
            }
        )
        cfg.setdefault("speech", {}).update(
            {
                "persona": self._persona_value(),
                "max_chars": int(self.var_max_chars.get()),
                "typewriter": bool(self.var_typewriter.get()),
                "bubble_seconds": int(self.var_bubble_seconds.get()),
            }
        )
        cfg.setdefault("behavior", {}).update(
            {
                "idle_animation": bool(self.var_idle_animation.get()),
                "auto_sleep_seconds": int(self.var_auto_sleep.get()),
                "greet_on_start": bool(self.var_greet.get()),
                "wheel_resize": bool(self.var_wheel_resize.get()),
                "click_actions": bool(self.var_click_actions.get()),
            }
        )
        cfg.setdefault("system", {}).update(
            {
                "autostart": bool(self.var_autostart.get()),
                "tray": bool(self.var_tray.get()),
            }
        )
        return cfg

    # ------------------------------------------------------------------
    # 预览 / 保存 / 取消
    # ------------------------------------------------------------------
    def _refresh_labels(self) -> None:
        self.var_size_label.set(f"{int(self.var_size.get())} px")
        self.var_opacity_label.set(f"{int(self.var_opacity.get())}%")

    def _on_size_scale(self, _value: str) -> None:
        self._refresh_labels()
        if not self._loading:
            self._preview_visual()

    def _on_opacity_scale(self, _value: str) -> None:
        self._refresh_labels()
        if not self._loading:
            self._preview_visual()

    def _preview_visual(self) -> None:
        try:
            self.app.preview_settings(self._collect_config())
        except Exception:  # noqa: BLE001
            self.log.debug("预览设置失败", exc_info=True)

    def _toggle_key_visible(self) -> None:
        try:
            self.entry_key.configure(show="" if self.var_show_key.get() else "*")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # 平台切换（DeepSeek / 智谱 GLM）
    # ------------------------------------------------------------------
    def _provider_id(self) -> str:
        label = self.var_provider.get()
        for pid, preset in C.PROVIDERS.items():
            if preset["label"] == label:
                return pid
        return C.DEFAULT_PROVIDER

    def _model_choices(self) -> list[str]:
        preset = C.PROVIDERS.get(self._current_provider) or C.PROVIDERS[C.DEFAULT_PROVIDER]
        return list(preset.get("models") or C.MODEL_CHOICES)

    def _on_provider_selected(self, _event: Any = None) -> None:
        if self._loading:
            return
        pid = self._provider_id()
        if pid == self._current_provider:
            return
        # 当前 Key 存回原平台，再载入新平台预设
        self._provider_keys[self._current_provider] = self.var_api_key.get().strip()
        self._current_provider = pid
        preset = C.PROVIDERS[pid]
        self.var_api_key.set(self._provider_keys.get(pid, ""))
        self.var_base_url.set(preset["base_url"])
        self.var_model.set(preset["default_model"])
        try:
            self.model_combo.configure(values=self._model_choices())
        except tk.TclError:
            pass
        self.var_model_hint.set(f"默认 {preset['default_model']}；也可输入 {preset['label']} 自定义模型名")

    def save(self) -> None:
        cfg = self._collect_config()
        try:
            ok, message = self.app.apply_settings(cfg, persist=True)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("保存设置失败")
            messagebox.showerror("保存失败", f"保存设置时出错：{exc}", parent=self.win)
            return
        if not ok:
            messagebox.showerror("保存失败", message, parent=self.win)
            return
        if message:
            self.var_status.set(message)
        self.original_config = cfg
        self.close()

    def cancel(self) -> None:
        try:
            self.app.restore_settings(self.original_config)
        except Exception:  # noqa: BLE001
            self.log.debug("取消设置恢复失败", exc_info=True)
        self.close()

    def restore_defaults(self) -> None:
        if not messagebox.askyesno(
            "恢复默认设置",
            "确定要恢复全部默认设置吗？（API Key 会清空）",
            parent=self.win,
        ):
            return
        try:
            defaults = self.app.get_default_config()
        except Exception:  # noqa: BLE001
            defaults = config_module.default_config()
        self._load_config(defaults)
        self._preview_visual()
        self.var_status.set("已恢复默认值，点「保存」生效")
        try:
            self.app.preview_settings(defaults)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # 测试连接
    # ------------------------------------------------------------------
    def _test_connection(self) -> None:
        cfg = self._collect_config()
        if not api.effective_key(cfg):
            self.var_test_status.set("请先填写 API Key")
            self.var_test_color.set("#B42318")
            return
        self.test_button.configure(state="disabled")
        self.var_test_status.set("正在测试…")
        self.var_test_color.set("#66708A")

        def worker() -> None:
            try:
                client = api.DeepSeekClient(logger)
                result = client.test_connection(cfg)
            except Exception as exc:  # noqa: BLE001
                result = (False, f"测试失败：{exc}")
            self._test_queue.put(result)

        threading.Thread(target=worker, name="BlueWhaleTestConn", daemon=True).start()
        self._poll_test()

    def _poll_test(self) -> None:
        if self._closed:
            return
        try:
            ok, message = self._test_queue.get_nowait()
        except queue.Empty:
            self._test_poll = self.win.after(120, self._poll_test) if self.win else None
            return
        self._test_poll = None
        self.var_test_status.set(message)
        self.var_test_color.set("#067647" if ok else "#B42318")
        try:
            self.test_button.configure(state="normal")
        except tk.TclError:
            pass

    def _apply_test_color(self) -> None:
        try:
            self.test_label.configure(foreground=self.var_test_color.get())
        except (tk.TclError, AttributeError):
            pass

    # ------------------------------------------------------------------
    # 杂项
    # ------------------------------------------------------------------
    def _place(self, width: int, height: int) -> None:
        """优先放在宠物对面的屏幕一侧，避免遮挡聊天窗口（截图/演示更干净）。"""
        vx, vy, vw, vh = self._screen_rect()
        margin = int(round(32 * self.scale))
        pet_rect = None
        try:
            pet_rect = self.app.get_pet_rect()
        except Exception:  # noqa: BLE001
            pet_rect = None
        if pet_rect:
            pet_cx = pet_rect[0] + pet_rect[2] // 2
            if pet_cx < vx + vw // 2:
                x = vx + vw - width - margin
            else:
                x = vx + margin
        else:
            x = vx + (vw - width) // 2
        y = vy + (vh - height) // 2
        margin = int(round(32 * self.scale))
        x = max(vx + margin, min(x, vx + vw - width - margin))
        y = max(vy + margin, min(y, vy + vh - height - margin))
        try:
            self.win.geometry(f"{width}x{height}+{int(x)}+{int(y)}")
        except tk.TclError:
            pass

    def _screen_rect(self) -> tuple[int, int, int, int]:
        rect = platform_win.virtual_screen_rect()
        if rect:
            return rect
        try:
            return 0, 0, int(self.root.winfo_screenwidth()), int(self.root.winfo_screenheight())
        except tk.TclError:
            return 0, 0, 1920, 1080

    def open_data_dir(self) -> None:
        path = str(self.app.data_dir)
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])  # noqa: S603, S607
            else:
                subprocess.Popen(["xdg-open", path])  # noqa: S603, S607
        except Exception as exc:  # noqa: BLE001
            messagebox.showinfo("数据目录", f"数据目录：\n{path}\n\n（自动打开失败：{exc}）", parent=self.win)

    def about(self) -> None:
        cfg_path = getattr(self.app, "config_path", "")
        asset_info = getattr(self.app, "asset_root", "")
        message = (
            f"{C.APP_NAME} {C.APP_VERSION}\n"
            f"{C.APP_SUBTITLE}\n\n"
            f"程序位置：{getattr(self.app, 'app_root', '')}\n"
            f"资产目录：{asset_info}\n"
            f"数据目录：{self.app.data_dir}\n"
            f"配置文件：{cfg_path}\n\n"
            "基于 DeepSeek / 智谱 GLM 双平台 API 的 AI 桌宠；美术为蓝色大肥鱼非官方二创，仅供个人使用。\n"
            "开源许可：代码 MIT。"
        )
        messagebox.showinfo("关于蓝色大肥鱼", message, parent=self.win)

    def _on_close(self) -> None:
        self.save()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._test_poll is not None:
            try:
                self.win.after_cancel(self._test_poll)
            except tk.TclError:
                pass
            self._test_poll = None
        try:
            self.app.on_settings_closed()
        except Exception:  # noqa: BLE001
            self.log.debug("设置窗口关闭回调异常", exc_info=True)
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def focus(self) -> None:
        try:
            self.win.deiconify()
            self.win.lift()
            self.win.focus_force()
        except tk.TclError:
            pass
