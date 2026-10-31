"""聊天输入窗口（双击宠物打开）。

- 富文本对话记录（只读）+ 多行输入框 + 发送
- Enter 发送 / Shift+Enter 换行 / Esc 关闭
- 回复流式显示在宠物气泡；本窗口在完成时追加最终文本
"""
from __future__ import annotations

import logging
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any, Callable

import constants as C
import platform_win

logger = logging.getLogger("bluewhale.chat")

FONT_CANDIDATES = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "PingFang SC",
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "WenQuanYi Micro Hei",
    "WenQuanYi Zen Hei",
    "Segoe UI",
    "DejaVu Sans",
)


def pick_font_family(root: tk.Misc) -> str:
    try:
        available = set(tkfont.families(root))
    except tk.TclError:
        return "TkDefaultFont"
    for candidate in FONT_CANDIDATES:
        if candidate in available:
            return candidate
    return "TkDefaultFont"


class ChatWindow:
    def __init__(
        self,
        root: tk.Tk,
        app: Any,
        scale: float = 1.0,
        pet_rect_provider: Callable[[], tuple[int, int, int, int] | None] | None = None,
        logger_: logging.Logger | None = None,
    ) -> None:
        self.root = root
        self.app = app
        self.scale = max(0.5, float(scale or 1.0))
        self.pet_rect_provider = pet_rect_provider
        self.log = logger_ or logger
        self.busy = False
        self._closed = False
        family = pick_font_family(root)

        width = int(round(430 * self.scale))
        height = int(round(380 * self.scale))
        self.win = tk.Toplevel(root, class_=C.WM_CLASS)
        self.win.title("和大肥鱼聊天 - 蓝色大肥鱼")
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda _e: self.close())

        container = ttk.Frame(self.win, padding=int(round(10 * self.scale)))
        container.pack(fill="both", expand=True)
        header = ttk.Label(
            container,
            text="🐳 和大肥鱼聊天",
            font=(family, 12, "bold"),
        )
        header.pack(anchor="w", pady=(0, int(round(4 * self.scale))))

        transcript_frame = ttk.Frame(container)
        transcript_frame.pack(fill="both", expand=True)
        self.transcript = tk.Text(
            transcript_frame,
            height=10,
            wrap="word",
            font=(family, 10),
            state="disabled",
            relief="flat",
            bg="#F7F9FF",
            fg="#0B1330",
            padx=int(round(8 * self.scale)),
            pady=int(round(6 * self.scale)),
        )
        scroll = ttk.Scrollbar(transcript_frame, orient="vertical", command=self.transcript.yview)
        self.transcript.configure(yscrollcommand=scroll.set)
        # 先 pack 右侧固定宽度控件，再 pack 可扩展的 Text，避免 Text 抢占全部宽度
        scroll.pack(side="right", fill="y")
        self.transcript.pack(side="left", fill="both", expand=True)
        self.transcript.tag_configure("user", foreground="#2B4BD0", font=(family, 10, "bold"))
        self.transcript.tag_configure("assistant", foreground="#16324F", font=(family, 10))
        self.transcript.tag_configure("hint", foreground="#7A8499", font=(family, 9))

        input_frame = ttk.Frame(container)
        input_frame.pack(fill="x", pady=(int(round(6 * self.scale)), 0))
        self.entry = tk.Text(
            input_frame,
            height=3,
            wrap="word",
            font=(family, 10),
            relief="solid",
            borderwidth=1,
            padx=int(round(6 * self.scale)),
            pady=int(round(4 * self.scale)),
        )
        self.entry.bind("<Return>", self._on_return)
        self.entry.bind("<KP_Enter>", self._on_return)
        self.entry.bind("<Shift-Return>", lambda _e: None)

        button_frame = ttk.Frame(input_frame)
        self.send_button = ttk.Button(button_frame, text="发送", command=self.send)
        self.send_button.pack(fill="x", pady=(0, int(round(4 * self.scale))))
        self.clear_button = ttk.Button(button_frame, text="清空", command=self._clear_context)
        self.clear_button.pack(fill="x")
        # 先占右侧按钮列，再让输入框占据剩余宽度
        button_frame.pack(side="right", fill="y", padx=(int(round(6 * self.scale)), 0))
        self.entry.pack(side="left", fill="both", expand=True)

        bottom = ttk.Frame(container)
        bottom.pack(fill="x", pady=(int(round(4 * self.scale)), 0))
        self.status = ttk.Label(bottom, text="Enter 发送 · Shift+Enter 换行 · Esc 关闭", foreground="#66708A")
        self.hint = ttk.Label(bottom, text="", foreground="#B45309")
        self.hint.pack(side="right")
        self.status.pack(side="left")

        self._place(width, height)
        self.win.deiconify()
        self.win.lift()
        self.entry.focus_set()
        try:
            platform_win.set_window_title(self.win, "和大肥鱼聊天 - 蓝色大肥鱼")
        except Exception:  # noqa: BLE001
            pass
        self.append_system("想聊点什么？戳我、问我、或者让我夸夸你都可以～")

    # ------------------------------------------------------------------
    def _place(self, width: int, height: int) -> None:
        vx, vy, vw, vh = self._screen_rect()
        rect = self.pet_rect_provider() if self.pet_rect_provider else None
        if rect:
            px, py, pw, ph = rect
            x = px - width - int(round(12 * self.scale))
            if x < vx + int(round(8 * self.scale)):
                x = px + pw + int(round(12 * self.scale))
            y = py + ph - height
        else:
            x = vx + (vw - width) // 2
            y = vy + (vh - height) // 2
        x = max(vx, min(x, vx + vw - width))
        y = max(vy, min(y, vy + vh - height))
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

    # ------------------------------------------------------------------
    def _on_return(self, event: tk.Event) -> str | None:
        # Shift+Enter 换行
        if int(getattr(event, "state", 0)) & 0x0001:
            return None
        self.send()
        return "break"

    def send(self) -> None:
        if self.busy:
            return
        text = self.entry.get("1.0", "end").strip()
        if not text:
            return
        self.entry.delete("1.0", "end")
        self.append_user(text)
        self.set_busy(True, "蓝鲸正在想…")
        try:
            self.app.on_chat_send(text)
        except Exception:  # noqa: BLE001
            self.log.exception("发送聊天消息失败")
            self.finish_reply("呜……我刚刚走神了，再发一次好吗？", error=True)

    # ------------------------------------------------------------------
    def _append(self, prefix: str, text: str, tag: str) -> None:
        try:
            self.transcript.configure(state="normal")
            self.transcript.insert("end", f"{prefix}{text}\n\n", tag)
            self.transcript.see("end")
            self.transcript.configure(state="disabled")
        except tk.TclError:
            pass

    def append_user(self, text: str) -> None:
        self._append("你：", text, "user")

    def append_assistant(self, text: str) -> None:
        self._append("蓝鲸：", text, "assistant")

    def append_system(self, text: str) -> None:
        self._append("", text, "hint")

    def set_status(self, text: str, error: bool = False) -> None:
        try:
            self.status.configure(text=text, foreground="#B42318" if error else "#66708A")
        except tk.TclError:
            pass

    def set_hint(self, text: str) -> None:
        try:
            self.hint.configure(text=text)
        except tk.TclError:
            pass

    def set_busy(self, busy: bool, status: str | None = None) -> None:
        self.busy = busy
        try:
            self.send_button.configure(state="disabled" if busy else "normal")
            self.entry.configure(state="disabled" if busy else "normal")
        except tk.TclError:
            return
        if status:
            self.set_status(status)
        if not busy:
            try:
                self.entry.focus_set()
            except tk.TclError:
                pass

    def finish_reply(self, reply: str, error: bool = False) -> None:
        if self._closed:
            return
        if reply:
            self.append_assistant(reply)
        self.set_busy(False, "Enter 发送 · Shift+Enter 换行 · Esc 关闭")
        if error:
            self.set_status("这次没成功，可以再试一次；托盘 → 设置 里可以检查 API Key", error=True)

    def _clear_context(self) -> None:
        try:
            self.app.clear_context()
        except Exception:  # noqa: BLE001
            self.log.debug("清空上下文失败", exc_info=True)
        self.append_system("（已经忘记之前聊过的内容啦）")

    # ------------------------------------------------------------------
    def set_topmost(self, enabled: bool) -> None:
        """设置窗口打开时临时取消聊天窗置顶，避免遮住设置窗。"""
        try:
            self.win.attributes("-topmost", bool(enabled))
        except tk.TclError:
            pass

    def focus(self) -> None:
        try:
            self.win.deiconify()
            self.win.lift()
            self.win.focus_force()
            self.entry.focus_set()
        except tk.TclError:
            pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.app.on_chat_closed()
        except Exception:  # noqa: BLE001
            self.log.debug("聊天窗口关闭回调异常", exc_info=True)
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def destroy(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass

