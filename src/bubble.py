"""语音气泡窗口（SPEC §6：短句、流式打字机）。

- 独立 overrideredirect 置顶小窗，跟随宠物位置（上方/下方自动避让屏幕边缘）
- Windows：色键透明 + Canvas 圆角气泡；Linux：Pillow mask + XShape 剪裁（无 shaper 时白底兜底）
- 静态短句打字机效果；聊天流式逐段追加
- 文本/窗口资源随 hide/destroy 释放
"""
from __future__ import annotations

import logging
import tkinter as tk
import tkinter.font as tkfont
from typing import Any, Callable

from PIL import Image, ImageDraw

import constants as C
import platform_win
from anim.frames import alpha_to_mask_bytes

logger = logging.getLogger("bluewhale.bubble")

TEXT_COLOR = "#0B1330"
BORDER_COLOR = "#4D6BFE"
FILL_COLOR = "#FFFFFF"
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


def _rounded_points(x1: float, y1: float, x2: float, y2: float, radius: float) -> list[float]:
    r = max(0.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]


class Bubble:
    def __init__(
        self,
        root: tk.Tk,
        pet_rect_provider: Callable[[], tuple[int, int, int, int] | None],
        scale: float = 1.0,
        mode: str = "chroma",
        key_rgb: tuple[int, int, int] = C.DEFAULT_KEY_RGB,
        shaper: Any = None,
        logger_: logging.Logger | None = None,
    ) -> None:
        self.root = root
        self.pet_rect_provider = pet_rect_provider
        self.scale = max(0.5, float(scale or 1.0))
        self.mode = mode
        self.key_rgb = key_rgb
        self.key_color = "#{:02x}{:02x}{:02x}".format(*key_rgb)
        self.shaper = shaper
        self.log = logger_ or logger
        self.win: tk.Toplevel | None = None
        self.canvas: tk.Canvas | None = None
        self._font: tkfont.Font | None = None
        self._visible = False
        self._streaming = False
        self._full_text = ""
        self._layout: dict[str, Any] | None = None
        self._hide_after: str | None = None
        self._type_after: str | None = None
        self._typing_index = 0
        self._opaque_fallback = mode != "chroma" and shaper is None
        self._destroyed = False

    # ------------------------------------------------------------------
    # 基础尺寸（按 DPI scale 缩放）
    # ------------------------------------------------------------------
    def _px(self, value: float) -> int:
        return max(1, int(round(value * self.scale)))

    @property
    def visible(self) -> bool:
        return self._visible and not self._destroyed

    def _ensure_window(self) -> None:
        if self.win is not None or self._destroyed:
            return
        win = tk.Toplevel(self.root, class_=C.WM_CLASS)
        win.withdraw()
        win.overrideredirect(True)
        try:
            win.title("蓝鲸桌宠-气泡")
        except tk.TclError:
            pass
        try:
            win.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        background = FILL_COLOR if self._opaque_fallback else self.key_color
        if self.mode == "chroma":
            try:
                win.wm_attributes("-transparentcolor", self.key_color)
            except tk.TclError:
                self.log.info("气泡窗口不支持色键透明，使用白底兜底")
                self._opaque_fallback = True
                background = FILL_COLOR
        self.canvas = tk.Canvas(
            win,
            width=self._px(120),
            height=self._px(40),
            highlightthickness=0,
            bd=0,
            bg=background,
            takefocus=0,
        )
        self.canvas.pack(side="top", fill="both", expand=True)
        self.canvas.bind("<Button-1>", lambda _e: self.hide())
        win.bind("<Button-1>", lambda _e: self.hide())
        self.win = win
        self._pick_font()

    def _pick_font(self) -> None:
        family = "TkDefaultFont"
        try:
            available = set(tkfont.families(self.root))
            for candidate in FONT_CANDIDATES:
                if candidate in available:
                    family = candidate
                    break
        except tk.TclError:
            pass
        try:
            self._font = tkfont.Font(root=self.root, family=family, size=10, weight="normal")
        except tk.TclError:
            self._font = tkfont.Font(root=self.root, size=10)

    # ------------------------------------------------------------------
    # 文本排版与绘制
    # ------------------------------------------------------------------
    def _wrap_lines(self, text: str, max_text_width: int) -> list[str]:
        assert self._font is not None
        lines: list[str] = []
        current: list[str] = []
        current_width = 0
        for ch in text:
            if ch == "\n":
                lines.append("".join(current))
                current, current_width = [], 0
                continue
            try:
                width = self._font.measure(ch)
            except tk.TclError:
                width = self._px(10)
            if current and current_width + width > max_text_width:
                lines.append("".join(current))
                current = [ch]
                current_width = width
                if len(lines) >= 5:
                    break
            else:
                current.append(ch)
                current_width += width
        else:
            lines.append("".join(current))
        if len(lines) > 6:
            lines = lines[:6]
        if not lines:
            lines = [""]
        return lines

    def _measure_layout(self, text: str) -> dict[str, Any]:
        assert self._font is not None
        rect = self._pet_rect()
        pet_w = int(rect[2]) if rect else self._px(168)
        max_body_w = max(self._px(110), min(self._px(360), max(pet_w, self._px(140))))
        pad_x = self._px(10)
        pad_y = self._px(7)
        radius = self._px(9)
        tail_w = self._px(14)
        tail_h = self._px(8)
        line_height = int(self._font.metrics("linespace"))
        max_text_width = max(self._px(60), max_body_w - 2 * pad_x)
        lines = self._wrap_lines(text, max_text_width)
        text_width = max((self._font.measure(line) for line in lines), default=0)
        text_width = min(text_width, max_text_width)
        body_w = max(self._px(70), text_width + 2 * pad_x)
        body_h = max(self._px(30), len(lines) * line_height + 2 * pad_y)
        total_w = body_w
        total_h = body_h + tail_h
        return {
            "lines": lines,
            "width": total_w,
            "height": total_h,
            "body_w": body_w,
            "body_h": body_h,
            "pad_x": pad_x,
            "pad_y": pad_y,
            "radius": radius,
            "tail_w": tail_w,
            "tail_h": tail_h,
            "line_height": line_height,
        }

    def _render(self, text: str) -> None:
        self._ensure_window()
        if self.win is None or self.canvas is None:
            return
        layout = self._measure_layout(text)
        self._layout = layout
        width, height = layout["width"], layout["height"]
        self.canvas.config(width=width, height=height)
        self.canvas.delete("all")
        background = FILL_COLOR if self._opaque_fallback else self.key_color
        self.canvas.config(bg=background)
        tail = self._choose_tail(layout)
        layout["tail"] = tail
        body_top = layout["tail_h"] if tail == "up" else 0
        body_bottom = body_top + layout["body_h"]
        x1, y1 = 1, body_top + 1
        x2, y2 = width - 2, body_bottom - 1
        # 尾巴（先画，主体覆盖接缝）
        cx = width / 2
        if tail == "down":
            tail_pts = [cx - layout["tail_w"] / 2, body_bottom - 2, cx + layout["tail_w"] / 2, body_bottom - 2, cx, height - 1]
        else:
            tail_pts = [cx - layout["tail_w"] / 2, body_top + 2, cx + layout["tail_w"] / 2, body_top + 2, cx, 1]
        self.canvas.create_polygon(
            *tail_pts, fill=FILL_COLOR, outline=BORDER_COLOR, width=max(1, self._px(1.2))
        )
        self.canvas.create_polygon(
            *_rounded_points(x1, y1, x2, y2, layout["radius"]),
            smooth=True,
            splinesteps=12,
            fill=FILL_COLOR,
            outline=BORDER_COLOR,
            width=max(1, self._px(1.4)),
        )
        text_item_y = body_top + layout["pad_y"]
        self.canvas.create_text(
            layout["pad_x"],
            text_item_y,
            anchor="nw",
            text="\n".join(layout["lines"]),
            font=self._font,
            fill=TEXT_COLOR,
            justify="left",
        )
        self._apply_shape(width, height, layout)
        self._place_window(width, height, tail)
        if not self._visible:
            try:
                self.win.deiconify()
                self.win.lift()
                self.win.attributes("-topmost", True)
            except tk.TclError:
                self.log.debug("显示气泡窗口失败", exc_info=True)
            self._visible = True
            try:
                self.win.update_idletasks()
            except tk.TclError:
                pass
            # 映射后再应用 XShape（未映射窗口发形状请求可能 BadWindow）
            self._apply_shape(width, height, layout)
            if self.shaper is not None:
                try:
                    self.shaper.set_net_wm_pid(self.win)
                except Exception:  # noqa: BLE001
                    pass

    def _choose_tail(self, layout: dict[str, Any]) -> str:
        rect = self._pet_rect()
        if not rect:
            return "down"
        pet_x, pet_y, _pet_w, pet_h = rect
        vx, vy, _vw, _vh = self._screen_rect()
        gap = self._px(6)
        above_y = pet_y - layout["height"] - gap
        if above_y >= vy + self._px(2):
            return "down"
        below_y = pet_y + pet_h + gap
        if below_y + layout["height"] <= vy + self._screen_rect()[3]:
            return "up"
        return "down"

    def _place_window(self, width: int, height: int, tail: str) -> None:
        assert self.win is not None
        rect = self._pet_rect()
        vx, vy, vw, vh = self._screen_rect()
        gap = self._px(6)
        if rect:
            pet_x, pet_y, pet_w, pet_h = rect
            x = pet_x + pet_w // 2 - width // 2
            if tail == "down":
                y = pet_y - height - gap
            else:
                y = pet_y + pet_h + gap
        else:
            x = vx + vw // 2 - width // 2
            y = vy + vh // 2 - height // 2
        x = max(vx, min(x, vx + vw - width))
        y = max(vy, min(y, vy + vh - height))
        try:
            self.win.geometry(f"{width}x{height}+{int(x)}+{int(y)}")
        except tk.TclError:
            self.log.debug("设置气泡几何失败", exc_info=True)

    def _apply_shape(self, width: int, height: int, layout: dict[str, Any]) -> None:
        if self.mode != "shape" or self.shaper is None or self.canvas is None or self.win is None:
            return
        if not self._visible:
            return
        try:
            mask_image = Image.new("L", (width, height), 0)
            draw = ImageDraw.Draw(mask_image)
            body_top = layout["tail_h"] if layout.get("tail") == "up" else 0
            body_bottom = body_top + layout["body_h"]
            draw.rounded_rectangle(
                [1, body_top + 1, width - 2, body_bottom - 1],
                radius=layout["radius"],
                fill=255,
            )
            cx = width / 2
            if layout.get("tail") == "down":
                draw.polygon(
                    [(cx - layout["tail_w"] / 2, body_bottom - 2), (cx + layout["tail_w"] / 2, body_bottom - 2), (cx, height - 1)],
                    fill=255,
                )
            else:
                draw.polygon(
                    [(cx - layout["tail_w"] / 2, body_top + 2), (cx + layout["tail_w"] / 2, body_top + 2), (cx, 1)],
                    fill=255,
                )
            mask = alpha_to_mask_bytes(mask_image)
            self.shaper.apply_mask(mask, width, height, self.canvas, self.win)
        except Exception:  # noqa: BLE001
            self.log.debug("气泡 XShape 应用失败（忽略）", exc_info=True)

    # ------------------------------------------------------------------
    # 位置来源
    # ------------------------------------------------------------------
    def _pet_rect(self) -> tuple[int, int, int, int] | None:
        try:
            rect = self.pet_rect_provider()
            if rect:
                return rect
        except Exception:  # noqa: BLE001
            self.log.debug("获取宠物位置失败", exc_info=True)
        return None

    def _screen_rect(self) -> tuple[int, int, int, int]:
        rect = platform_win.virtual_screen_rect()
        if rect:
            return rect
        try:
            return 0, 0, int(self.root.winfo_screenwidth()), int(self.root.winfo_screenheight())
        except tk.TclError:
            return 0, 0, 1920, 1080

    # ------------------------------------------------------------------
    # 对外：静态短句 / 流式
    # ------------------------------------------------------------------
    def show(self, text: str, seconds: float | None = None, typewriter: bool | None = None) -> None:
        if self._destroyed:
            return
        text = (text or "").strip()
        if not text:
            return
        self._cancel_timers()
        self._streaming = False
        self._full_text = text
        if typewriter:
            self._typing_index = 0
            self._render("")
            self._type_tick()
        else:
            self._render(text)
            self._schedule_hide(seconds)

    def _type_tick(self) -> None:
        self._type_after = None
        if self._destroyed or self._full_text == "":
            return
        self._typing_index = min(len(self._full_text), self._typing_index + 2)
        self._render(self._full_text[: self._typing_index])
        if self._typing_index < len(self._full_text):
            try:
                self._type_after = self.root.after(24, self._type_tick)
            except tk.TclError:
                self._type_after = None
        else:
            self._schedule_hide(None)

    def begin_stream(self, placeholder: str = "…") -> None:
        if self._destroyed:
            return
        self._cancel_timers()
        self._streaming = True
        self._full_text = placeholder
        self._render(placeholder)

    def append_stream(self, delta: str) -> None:
        if self._destroyed or not self._streaming or not delta:
            return
        self._full_text = (self._full_text if self._full_text != "…" else "") + delta
        if len(self._full_text) > 240:
            self._full_text = self._full_text[:240]
        self._render(self._full_text)

    def replace_stream_text(self, text: str) -> None:
        if self._destroyed:
            return
        self._full_text = text or ""
        self._render(self._full_text)

    def end_stream(self, final_text: str | None = None, seconds: float | None = None) -> None:
        if self._destroyed:
            return
        self._streaming = False
        if final_text is not None:
            self._full_text = final_text
        if self._full_text:
            self._render(self._full_text)
            self._schedule_hide(seconds)

    @property
    def streaming(self) -> bool:
        return self._streaming

    def _schedule_hide(self, seconds: float | None) -> None:
        if self._hide_after is not None:
            try:
                self.root.after_cancel(self._hide_after)
            except tk.TclError:
                pass
        delay = 7.0 if seconds is None else max(0.5, float(seconds))
        try:
            self._hide_after = self.root.after(int(delay * 1000), self.hide)
        except tk.TclError:
            self._hide_after = None

    def _cancel_timers(self) -> None:
        for attr in ("_hide_after", "_type_after"):
            after_id = getattr(self, attr)
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
                setattr(self, attr, None)

    def reposition(self) -> None:
        if self._visible and self._layout is not None:
            self._render(self._full_text)

    def hide(self) -> None:
        self._cancel_timers()
        self._streaming = False
        self._visible = False
        if self.win is not None:
            try:
                self.win.withdraw()
            except tk.TclError:
                pass

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self._cancel_timers()
        if self.shaper is not None and self.canvas is not None and self.win is not None:
            try:
                self.shaper.clear(self.canvas, self.win)
            except Exception:  # noqa: BLE001
                pass
        self._layout = None
        self._font = None
        if self.canvas is not None:
            try:
                self.canvas.destroy()
            except tk.TclError:
                pass
            self.canvas = None
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
            self.win = None
        self._visible = False
