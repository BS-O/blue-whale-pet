"""透明置顶无边框宠物窗口（SPEC §3）。

- Windows：``-transparentcolor`` 色键 + Pillow 合成；ctypes 同时设置色键与整窗 alpha
- Linux：Pillow mask + ctypes XShape 剪裁（失败回退 -alpha）
- 交互：左键戳 / 双击聊天 / 右键拖拽移动 / 右键单击菜单 / 滚轮缩放
- DPI：config 中 size/x/y 为逻辑像素，窗口实际像素 = logical * scale（125% 下清晰不虚）
"""
from __future__ import annotations

import logging
import tkinter as tk
from typing import Any, Callable

import constants as C
import platform_win
import resources
from anim.manifest import Manifest

logger = logging.getLogger("bluewhale.pet_window")


class PetWindow:
    """宠物主窗口。通过 callbacks 把交互交给 PetApp。"""

    def __init__(
        self,
        root: tk.Tk,
        config: dict[str, Any],
        manifest: Manifest,
        callbacks: Any,
        scale: float = 1.0,
        sprite_mode: str = "chroma",
        shaper: Any = None,
    ) -> None:
        self.root = root
        self.cfg = config
        self.manifest = manifest
        self.callbacks = callbacks
        self.scale = max(0.5, float(scale or 1.0))
        self.sprite_mode = sprite_mode
        self.shaper = shaper
        self.log = logger
        self.key_rgb = manifest.key_rgb
        self.key_color = manifest.key_color

        pet_cfg = config.get("pet") or {}
        self.logical_size = C.MIN_SIZE
        self.pixel_w = 0
        self.pixel_h = 0
        self.visible = False
        self._photo: Any = None
        self._mask: bytes | None = None
        self._bob = 0
        self._click_after: str | None = None
        self._suppress_release = False
        self._right_press: tuple[int, int, int, int] | None = None
        self._right_dragged = False
        self._destroyed = False
        self._after_ids: list[str] = []
        # 位置以“目标坐标”为准：winfo_x/y 在 geometry 请求后可能还未刷新，
        # 拖动/程序移动后立刻持久化会读到旧值，因此这里自行记录。
        self._position: tuple[int, int] | None = None

        self.win = tk.Toplevel(root, class_=C.WM_CLASS)
        self.win.withdraw()
        self.win.overrideredirect(True)
        try:
            self.win.title(C.PET_WINDOW_TITLE)
        except tk.TclError:
            pass
        try:
            self.win.wm_attributes("-topmost", bool(pet_cfg.get("always_on_top", True)))
        except tk.TclError:
            pass
        try:
            icon = resources.app_icon_path()
            if icon.is_file():
                self.win.iconbitmap(str(icon))
        except (tk.TclError, OSError):
            pass

        # Windows 色键透明（Linux 用 XShape）
        self._colorkey_applied = False
        if self.sprite_mode == "chroma":
            try:
                self.win.wm_attributes("-transparentcolor", self.key_color)
                self._colorkey_applied = True
            except tk.TclError:
                self.log.info("当前平台不支持 -transparentcolor，改用窗口形状/alpha 兜底")

        self.canvas = tk.Canvas(
            self.win,
            width=1,
            height=1,
            highlightthickness=0,
            bd=0,
            bg=self.key_color,
            takefocus=0,
            cursor="hand2",
        )
        self.canvas.pack(side="top", fill="both", expand=True)
        self._image_id = self.canvas.create_image(0, 0, image=None, anchor="center")
        self._bind_events()

        self.logical_size = self._clamp_size(pet_cfg.get("size") or C.DEFAULT_SIZE)
        self._compute_pixel_size()
        self._apply_geometry(initial=True)
        self._apply_position_from_config(pet_cfg)
        self._apply_opacity(pet_cfg.get("opacity", 1.0))
        click_through = bool(pet_cfg.get("click_through"))
        if click_through:
            self.set_click_through(True)

    # ------------------------------------------------------------------
    # 尺寸 / 位置（逻辑像素 ↔ 物理像素）
    # ------------------------------------------------------------------
    @staticmethod
    def _clamp_size(value: Any) -> int:
        try:
            size = int(round(float(value)))
        except (TypeError, ValueError):
            size = C.DEFAULT_SIZE
        return max(C.MIN_SIZE, min(C.MAX_SIZE, size))

    def _compute_pixel_size(self) -> None:
        self.pixel_w = max(16, int(round(self.logical_size * self.scale)))
        aspect = self.manifest.aspect
        self.pixel_h = max(16, int(round(self.pixel_w * aspect)))

    def _screen_rect(self) -> tuple[int, int, int, int]:
        rect = platform_win.virtual_screen_rect()
        if rect:
            return rect
        try:
            vx, vy = 0, 0
            vw = int(self.win.winfo_screenwidth())
            vh = int(self.win.winfo_screenheight())
            if vw > 0 and vh > 0:
                return vx, vy, vw, vh
        except tk.TclError:
            pass
        return 0, 0, 1920, 1080

    def clamp_position(self, x: int, y: int) -> tuple[int, int]:
        vx, vy, vw, vh = self._screen_rect()
        if self.pixel_w <= vw:
            x = max(vx, min(x, vx + vw - self.pixel_w))
        else:
            x = vx
        if self.pixel_h <= vh:
            y = max(vy, min(y, vy + vh - self.pixel_h))
        else:
            y = vy
        return int(x), int(y)

    def default_position(self) -> tuple[int, int]:
        vx, vy, vw, vh = self._screen_rect()
        x = vx + vw - self.pixel_w - int(round(40 * self.scale))
        y = vy + vh - self.pixel_h - int(round(80 * self.scale))
        return self.clamp_position(x, y)

    def _apply_geometry(self, initial: bool = False) -> None:
        """按当前 pixel_w/h 设置窗口尺寸并保持可视区域。"""
        if initial:
            self.win.geometry(f"{self.pixel_w}x{self.pixel_h}")
        self.canvas.config(width=self.pixel_w, height=self.pixel_h)
        self.canvas.coords(self._image_id, self.pixel_w // 2, self.pixel_h // 2 + self._bob)

    def _apply_position_from_config(self, pet_cfg: dict[str, Any]) -> None:
        x = pet_cfg.get("x")
        y = pet_cfg.get("y")
        if x is None or y is None:
            px, py = self.default_position()
        else:
            try:
                px = int(round(float(x) * self.scale))
                py = int(round(float(y) * self.scale))
            except (TypeError, ValueError):
                px, py = self.default_position()
        px, py = self.clamp_position(px, py)
        self._position = (px, py)
        self.win.geometry(f"+{px}+{py}")

    def position(self) -> tuple[int, int]:
        """物理像素坐标（优先目标坐标，避免 winfo 刷新延迟导致持久化旧值）。"""
        if self._position is not None:
            return self._position
        try:
            return int(self.win.winfo_x()), int(self.win.winfo_y())
        except tk.TclError:
            return 0, 0

    def logical_position(self) -> tuple[int, int]:
        px, py = self.position()
        return int(round(px / self.scale)), int(round(py / self.scale))

    def move_to_physical(self, x: int, y: int) -> None:
        x, y = self.clamp_position(int(x), int(y))
        self._position = (x, y)
        self.win.geometry(f"+{x}+{y}")

    def move_to_logical(self, x: int, y: int) -> None:
        self.move_to_physical(int(round(x * self.scale)), int(round(y * self.scale)))

    # ------------------------------------------------------------------
    # 对外更新接口
    # ------------------------------------------------------------------
    def set_frame(self, photo: Any, mask: bytes | None = None) -> None:
        if self._destroyed or photo is None:
            return
        self._photo = photo
        self._mask = mask
        self.canvas.itemconfigure(self._image_id, image=photo)
        self.canvas.coords(self._image_id, self.pixel_w // 2, self.pixel_h // 2 + self._bob)
        self._apply_shape(mask)

    def _apply_shape(self, mask: bytes | None) -> None:
        if self.sprite_mode != "shape" or self.shaper is None or not mask:
            return
        if not self.visible:
            # 窗口尚未映射：X11 下对未映射窗口发形状请求可能 BadWindow，
            # 推迟到 show() 之后应用（self._mask 已保存最新帧）
            return
        try:
            self.shaper.apply_mask(mask, self.pixel_w, self.pixel_h, self.canvas, self.win)
        except Exception:  # noqa: BLE001
            self.log.debug("XShape 应用失败（忽略）", exc_info=True)

    def set_bob(self, offset: int) -> None:
        """待机呼吸：图像在窗口内上下偏移 0~2px（不移动窗口）。"""
        if self._destroyed:
            return
        offset = max(-4, min(4, int(offset)))
        if offset == self._bob:
            return
        self._bob = offset
        self.canvas.coords(self._image_id, self.pixel_w // 2, self.pixel_h // 2 + self._bob)

    def resize_logical(self, logical_size: int) -> None:
        new_size = self._clamp_size(logical_size)
        if new_size == self.logical_size:
            return
        old_w, old_h = self.pixel_w, self.pixel_h
        old_x, old_y = self.position()
        self.logical_size = new_size
        self._compute_pixel_size()
        self.win.geometry(f"{self.pixel_w}x{self.pixel_h}")
        self.canvas.config(width=self.pixel_w, height=self.pixel_h)
        # 以中心为基准调整位置，避免变大后跑偏
        new_x = old_x + (old_w - self.pixel_w) // 2
        new_y = old_y + (old_h - self.pixel_h) // 2
        self.move_to_physical(new_x, new_y)
        if self.visible:
            self._reapply_layered()
        callback = getattr(self.callbacks, "on_size_changed", None)
        if callback is not None:
            try:
                callback(self.logical_size)
            except Exception:  # noqa: BLE001
                self.log.error("on_size_changed 回调异常", exc_info=True)

    def set_opacity(self, opacity: float) -> None:
        try:
            value = max(0.3, min(1.0, float(opacity)))
        except (TypeError, ValueError):
            value = 1.0
        self._apply_opacity(value)

    def _apply_opacity(self, opacity: Any) -> None:
        try:
            value = max(0.3, min(1.0, float(opacity)))
        except (TypeError, ValueError):
            value = 1.0
        if platform_win.IS_WINDOWS:
            hwnd = platform_win.get_root_hwnd(self.win)
            platform_win.apply_layered(hwnd, self.key_rgb, value)
        else:
            try:
                self.win.attributes("-alpha", value)
            except tk.TclError:
                pass

    def _reapply_layered(self) -> None:
        if platform_win.IS_WINDOWS:
            hwnd = platform_win.get_root_hwnd(self.win)
            self._after(60, lambda: platform_win.apply_layered(hwnd, self.key_rgb, self._current_opacity()))
        elif self.sprite_mode == "alpha":
            try:
                self.win.attributes("-alpha", self._current_opacity())
            except tk.TclError:
                pass

    def _current_opacity(self) -> float:
        try:
            return max(0.3, min(1.0, float((self.cfg.get("pet") or {}).get("opacity", 1.0))))
        except (TypeError, ValueError):
            return 1.0

    def set_always_on_top(self, enabled: bool) -> None:
        try:
            self.win.attributes("-topmost", bool(enabled))
        except tk.TclError:
            self.log.debug("设置置顶失败", exc_info=True)
        if enabled and self.visible:
            try:
                self.win.lift()
            except tk.TclError:
                pass
        self._reapply_layered()

    def set_click_through(self, enabled: bool) -> None:
        if not platform_win.IS_WINDOWS:
            self.log.info("当前平台不支持鼠标穿透")
            return
        hwnd = platform_win.get_root_hwnd(self.win)
        if not hwnd:
            return
        platform_win.set_click_through(hwnd, enabled)
        if not enabled:
            self._reapply_layered()

    # ------------------------------------------------------------------
    # 显示 / 隐藏
    # ------------------------------------------------------------------
    def show(self, focus: bool = False) -> None:
        if self._destroyed:
            return
        try:
            self.win.deiconify()
            self.win.lift()
            if (self.cfg.get("pet") or {}).get("always_on_top", True):
                self.win.attributes("-topmost", True)
        except tk.TclError:
            self.log.exception("显示宠物窗口失败")
        self.visible = True
        try:
            self.win.update_idletasks()
        except tk.TclError:
            pass
        # 映射后再应用异形窗口（Linux XShape；Windows 下 no-op）
        self._apply_shape(self._mask)
        if self.shaper is not None:
            try:
                self.shaper.set_net_wm_pid(self.win)
            except Exception:  # noqa: BLE001
                pass
        if self._colorkey_applied:
            try:
                # 重新声明色键（映射/样式变化后 Tk 可能重置分层属性）
                self.win.wm_attributes("-transparentcolor", self.key_color)
            except tk.TclError:
                pass
        self._reapply_layered()
        try:
            platform_win.set_window_title(self.win, C.PET_WINDOW_TITLE)
        except Exception:  # noqa: BLE001
            pass
        if focus:
            platform_win.set_foreground(self.win)

    def hide(self) -> None:
        if self._destroyed:
            return
        try:
            self.win.withdraw()
        except tk.TclError:
            pass
        self.visible = False

    def toggle(self) -> bool:
        if self.visible:
            self.hide()
        else:
            self.show()
        return self.visible

    def raise_(self) -> None:
        try:
            self.win.lift()
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # 事件绑定
    # ------------------------------------------------------------------
    def _bind_events(self) -> None:
        target = self.canvas
        target.bind("<ButtonPress-1>", self._on_left_press, add="+")
        target.bind("<ButtonRelease-1>", self._on_left_release, add="+")
        target.bind("<Double-Button-1>", self._on_double_click, add="+")
        target.bind("<ButtonPress-3>", self._on_right_press, add="+")
        target.bind("<B3-Motion>", self._on_right_motion, add="+")
        target.bind("<ButtonRelease-3>", self._on_right_release, add="+")
        target.bind("<MouseWheel>", self._on_wheel_windows, add="+")
        target.bind("<Button-4>", lambda event: self._emit_wheel(+1), add="+")
        target.bind("<Button-5>", lambda event: self._emit_wheel(-1), add="+")
        try:
            self.win.bind("<ButtonPress-1>", self._on_left_press, add="+")
            self.win.bind("<ButtonRelease-1>", self._on_left_release, add="+")
            self.win.bind("<Double-Button-1>", self._on_double_click, add="+")
            self.win.bind("<ButtonPress-3>", self._on_right_press, add="+")
            self.win.bind("<B3-Motion>", self._on_right_motion, add="+")
            self.win.bind("<ButtonRelease-3>", self._on_right_release, add="+")
        except tk.TclError:
            pass

    def _notify(self, name: str, *args: Any) -> None:
        callback = getattr(self.callbacks, name, None)
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:  # noqa: BLE001
            self.log.exception("交互回调 %s 异常", name)

    def _on_left_press(self, event: tk.Event) -> None:
        self._notify("mark_interaction")

    def _on_left_release(self, event: tk.Event) -> None:
        if self._suppress_release:
            self._suppress_release = False
            return
        if self._click_after is not None:
            try:
                self.win.after_cancel(self._click_after)
            except tk.TclError:
                pass
        self._click_after = self._after(230, self._fire_poke)

    def _fire_poke(self) -> None:
        self._click_after = None
        self._notify("on_poke")

    def _on_double_click(self, event: tk.Event) -> None:
        if self._click_after is not None:
            try:
                self.win.after_cancel(self._click_after)
            except tk.TclError:
                pass
            self._click_after = None
        self._suppress_release = True
        self._notify("on_double_click")

    def _cursor_pos(self, event: tk.Event) -> tuple[int, int]:
        """优先用真实光标位置（拖动窗口时 Tk 的 x_root 可能漂移）。"""
        pos = platform_win.get_cursor_pos()
        if pos is not None:
            return pos
        return int(event.x_root), int(event.y_root)

    def _on_right_press(self, event: tk.Event) -> None:
        self._notify("mark_interaction")
        cursor = self._cursor_pos(event)
        self._right_press = (cursor[0], cursor[1], self.position()[0], self.position()[1])
        self._right_dragged = False

    def _on_right_motion(self, event: tk.Event) -> None:
        if self._right_press is None:
            return
        sx, sy, wx, wy = self._right_press
        cx, cy = self._cursor_pos(event)
        dx = cx - sx
        dy = cy - sy
        if not self._right_dragged and abs(dx) + abs(dy) > max(4, int(4 * self.scale)):
            self._right_dragged = True
            self._notify("on_drag_start")
        if self._right_dragged:
            self.move_to_physical(wx + dx, wy + dy)

    def _on_right_release(self, event: tk.Event) -> None:
        pressed = self._right_press
        self._right_press = None
        if pressed is None:
            return
        if self._right_dragged:
            self._right_dragged = False
            self._notify("on_drag_end")
        else:
            self._notify("on_context_menu", int(event.x_root), int(event.y_root))

    def _on_wheel_windows(self, event: tk.Event) -> None:
        try:
            delta = int(getattr(event, "delta", 0))
        except (TypeError, ValueError):
            delta = 0
        if delta > 0:
            self._emit_wheel(+1)
        elif delta < 0:
            self._emit_wheel(-1)

    def _emit_wheel(self, direction: int) -> None:
        self._notify("mark_interaction")
        self._notify("on_wheel", int(direction))

    # ------------------------------------------------------------------
    # 定时器 / 清理
    # ------------------------------------------------------------------
    def _after(self, delay_ms: int, callback: Callable[[], None]) -> str | None:
        if self._destroyed:
            return None
        try:
            after_id = self.win.after(int(delay_ms), callback)
        except tk.TclError:
            return None
        self._after_ids.append(after_id)
        # 保持列表精简
        if len(self._after_ids) > 64:
            self._after_ids = self._after_ids[-32:]
        return after_id

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        if self._click_after is not None:
            try:
                self.win.after_cancel(self._click_after)
            except tk.TclError:
                pass
            self._click_after = None
        for after_id in self._after_ids:
            try:
                self.win.after_cancel(after_id)
            except tk.TclError:
                pass
        self._after_ids.clear()
        self._photo = None
        self._mask = None
        if self.shaper is not None:
            try:
                self.shaper.clear(self.canvas, self.win)
            except Exception:  # noqa: BLE001
                pass
        try:
            self.canvas.destroy()
        except tk.TclError:
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        self.visible = False
