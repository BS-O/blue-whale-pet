"""蓝鲸桌宠 - 占位入口（pet-core 将用完整实现替换本文件）。
仅用于早期打包流水线联调：py src/main.py 应显示一只占位蓝鲸。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

APP_VERSION = "1.0.0"
APP_NAME = "蓝鲸桌宠"


def asset_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


def main() -> int:
    args = sys.argv[1:]
    if "--version" in args:
        print(f"{APP_NAME} {APP_VERSION}")
        return 0
    if "--selftest" in args:
        manifest = json.loads((asset_root() / "mascot" / "manifest.json").read_text(encoding="utf-8"))
        print(f"SELFTEST OK {{\"placeholder\": true, \"states\": {len(manifest['states'])}}}")
        return 0
    try:
        import tkinter as tk
        from PIL import Image, ImageTk
    except Exception as exc:  # pragma: no cover - 占位实现
        print(f"依赖缺失: {exc}", file=sys.stderr)
        return 1
    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry("240x240+400+200")
    root.attributes("-topmost", True)
    root.overrideredirect(True)
    img = Image.open(asset_root() / "mascot" / "master" / "idle_0.png").convert("RGBA")
    bg = Image.new("RGB", img.size, (1, 2, 3))
    bg.paste(img, (0, 0), img)
    photo = ImageTk.PhotoImage(bg.resize((240, 240), Image.LANCZOS))
    canvas = tk.Canvas(root, width=240, height=240, highlightthickness=0, bg="#010203")
    canvas.pack()
    canvas.create_image(120, 120, image=photo)
    root.attributes("-transparentcolor", "#010203")
    root.after(4000, root.destroy)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
