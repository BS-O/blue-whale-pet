# -*- coding: utf-8 -*-
"""桌宠精灵 v5：直接使用桌面"1"文件夹的状态图（抠图后按状态组装）。

素材（Desktop/1/）：happy/love/play/sad/say/sleep/what.png + 4.jpg
映射：
  idle/blink/eat/happy/laugh ← happy.png   talk ← say.png(自带气泡)
  think/surprise ← what.png(自带问号)       sad ← sad.png
  sleep ← sleep.png(自带Zzz)                love ← love.png
  wave/drag/angry(50% 愤怒版) ← play.png    angry_alt(50%) ← 4.jpg
输出 assets/mascot/master/ 40 帧；manifest 不变（angry_alt 已存在）。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_sources import flood_remove_bg  # noqa: E402

DESK1 = Path(r"C:\Users\38495\Desktop\1")
MASTER = ROOT / "assets" / "mascot" / "master"
CANVAS = 512
FIT_H = 466
FIT_W = 470

COL = {
    "heart": (255, 90, 121, 255),
    "anger": (229, 72, 77, 255),
    "note": (139, 92, 246, 255),
    "speed": (154, 167, 199, 255),
    "crumb": (244, 162, 97, 255),
    "wave": (120, 145, 200, 255),
}

BODIES: dict[str, Image.Image] = {}


def load_body(stem: str) -> Image.Image:
    p = DESK1 / f"{stem}.jpg" if stem == "4" else DESK1 / f"{stem}.png"
    im = Image.open(p)
    rgba, ratio = flood_remove_bg(im)
    bbox = rgba.getchannel("A").getbbox()
    if bbox and 0.05 < ratio < 0.92:
        rgba = rgba.crop(bbox)
    else:
        # 抠图失败（背景复杂）→ 中心方形圆角裁切
        w, h = rgba.size
        side = min(w, h)
        rgba = rgba.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
        mask = Image.new("L", (side * 2, side * 2), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, side * 2 - 1, side * 2 - 1), radius=side // 2, fill=255)
        rgba.putalpha(mask.resize((side, side), Image.LANCZOS))
    rgba = rgba.filter(ImageFilter.UnsharpMask(radius=1.8, percent=100, threshold=2))
    rgba = ImageEnhance.Color(rgba).enhance(1.08)
    return rgba


def draw_heart(d: ImageDraw.ImageDraw, cx: int, cy: int, s: int, fill) -> None:
    import math
    pts = []
    for i in range(26):
        a = math.tau * i / 26
        x = 16 * math.sin(a) ** 3
        y = -(13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a))
        pts.append((cx + x * s / 16, cy + y * s / 16))
    d.polygon(pts, fill=fill)


def draw_symbol(layer: Image.Image, kind: str) -> None:
    d = ImageDraw.Draw(layer)
    W, H = layer.size
    if kind == "anger":
        cx, cy, s = int(W * 0.78), int(H * 0.12), 24
        import math
        for a in (15, 75, 165, 255):
            rad = math.radians(a)
            x2, y2 = cx + s * math.cos(rad), cy - s * math.sin(rad)
            d.line((cx - x2 + cx, cy - y2 + cy, x2, y2), fill=COL["anger"], width=8)
    elif kind == "heart":
        draw_heart(d, int(W * 0.82), int(H * 0.14), 26, COL["heart"])
        draw_heart(d, int(W * 0.90), int(H * 0.26), 16, COL["heart"])
    elif kind == "note":
        d.ellipse((W * 0.80, H * 0.18, W * 0.80 + 16, H * 0.18 + 12), fill=COL["note"])
        d.line((W * 0.80 + 14, H * 0.18, W * 0.80 + 14, H * 0.08), fill=COL["note"], width=4)
        d.line((W * 0.80 + 14, H * 0.08, W * 0.80 + 30, H * 0.12), fill=COL["note"], width=4)
    elif kind == "speed":
        for i in range(3):
            y = H * (0.32 + i * 0.15)
            d.line((W * 0.08, y, W * 0.26, y), fill=COL["speed"], width=7)
    elif kind == "crumb":
        for i in range(4):
            cx, cy = W * (0.46 + (i % 2) * 0.08), H * (0.30 + (i // 2) * 0.05)
            s = 6 - i // 2
            d.ellipse((cx - s, cy - s, cx + s, cy + s), fill=COL["crumb"])
    elif kind == "wave":
        import math
        cx, cy = W * 0.82, H * 0.16
        pts = [(cx + i * 6, cy + (9 if i % 2 else -9)) for i in range(9)]
        d.line(pts, fill=COL["wave"], width=6, joint="curve")


def compose(body: Image.Image, spec: dict) -> Image.Image:
    squash, rot, dx, dy = spec["t"]
    w, h = body.size
    scale = min(FIT_H / h, FIT_W / w)
    w2, h2 = max(1, int(w * scale)), max(1, int(h * scale))
    h3 = max(1, int(h2 * squash))
    img = body.resize((w2, h3), Image.LANCZOS)
    if rot:
        img = img.rotate(rot, expand=True, resample=Image.BICUBIC)
    if spec.get("dark"):
        img = ImageEnhance.Brightness(img).enhance(spec["dark"])
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.alpha_composite(img, ((CANVAS - img.width) // 2 + dx, CANVAS - img.height + dy))
    if spec.get("sym"):
        sym = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        draw_symbol(sym, spec["sym"])
        canvas.alpha_composite(sym)
    return canvas


FRAMES: dict[str, list[dict]] = {
    "idle": [
        dict(body="happy", t=(1.00, 0, 0, 0)),
        dict(body="happy", t=(0.97, 0, 0, 2)),
        dict(body="happy", t=(0.94, 0, 0, 4)),
        dict(body="happy", t=(0.97, 0, 0, 2)),
    ],
    "blink": [
        dict(body="happy", t=(1.00, 0, 0, 0)),
        dict(body="happy", t=(0.96, 0, 0, 2)),
        dict(body="happy", t=(0.99, 0, 0, 1)),
    ],
    "happy": [
        dict(body="happy", t=(1.00, -3, 0, 0)),
        dict(body="happy", t=(0.94, 3, 0, 3)),
        dict(body="happy", t=(0.98, -2, 0, 1)),
    ],
    "laugh": [
        dict(body="happy", t=(1.02, -4, 0, -2), sym="note"),
        dict(body="happy", t=(0.92, 5, 0, 5), sym="note"),
        dict(body="happy", t=(0.97, 0, 0, 2), sym="note"),
    ],
    "talk": [
        dict(body="say", t=(1.00, 0, 0, 0)),
        dict(body="say", t=(0.96, 2, 1, 3)),
        dict(body="say", t=(0.99, -2, -1, 1)),
    ],
    "think": [
        dict(body="what", t=(1.00, 4, 2, 0)),
        dict(body="what", t=(0.98, 5, 3, 1)),
        dict(body="what", t=(0.99, 3, 2, 0)),
    ],
    "sleep": [
        dict(body="sleep", t=(1.00, 0, 0, 0), dark=0.96),
        dict(body="sleep", t=(0.96, 0, 0, 2), dark=0.92),
        dict(body="sleep", t=(0.98, 0, 0, 1), dark=0.94),
    ],
    "surprise": [
        dict(body="what", t=(1.05, 0, 0, -3)),
        dict(body="what", t=(1.07, 0, 0, -4)),
    ],
    "sad": [
        dict(body="sad", t=(0.97, -4, -2, 2)),
        dict(body="sad", t=(0.95, -5, -3, 3)),
    ],
    "angry": [
        dict(body="play", t=(1.00, -2, -3, 0), sym="anger"),
        dict(body="play", t=(1.00, 2, 3, 0), sym="anger"),
    ],
    "angry_alt": [
        dict(body="4", t=(1.00, -2, -3, 0), sym="anger"),
        dict(body="4", t=(1.00, 2, 3, 0), sym="anger"),
    ],
    "love": [
        dict(body="love", t=(1.00, 0, 0, 0), sym="heart"),
        dict(body="love", t=(0.95, 0, 0, 4), sym="heart"),
    ],
    "drag": [
        dict(body="play", t=(0.98, 12, 4, 0), sym="speed"),
        dict(body="play", t=(0.98, 14, 6, 0), sym="speed"),
    ],
    "wave": [
        dict(body="play", t=(0.98, -6, 0, 0)),
        dict(body="play", t=(0.98, 6, 0, 0), sym="wave"),
        dict(body="play", t=(0.98, -4, 0, 0)),
    ],
    "eat": [
        dict(body="happy", t=(1.00, 0, 0, 0), sym="crumb"),
        dict(body="happy", t=(0.95, 2, 0, 4), sym="crumb"),
        dict(body="happy", t=(0.97, -1, 0, 2), sym="crumb"),
    ],
}


def main() -> None:
    for stem in ("happy", "love", "play", "sad", "say", "sleep", "what", "4"):
        BODIES[stem] = load_body(stem)
    print("bodies:", {k: v.size for k, v in sorted(BODIES.items())})
    MASTER.mkdir(parents=True, exist_ok=True)
    total = 0
    for state, specs in FRAMES.items():
        base = "angryalt" if state == "angry_alt" else state
        for i, spec in enumerate(specs):
            compose(BODIES[spec["body"]], spec).save(MASTER / f"{base}_{i}.png")
            total += 1
    print(f"frames written: {total}")


if __name__ == "__main__":
    main()
