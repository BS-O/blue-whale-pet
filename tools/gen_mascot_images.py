# -*- coding: utf-8 -*-
"""桌宠精灵生成器 v3：多素材状态系统（用户桌面 1~5 号图）。

素材分工：
  - 5.png 主体（854×1564）→ idle / blink / drag（呼吸、wink、拖拽，效果最好）
  - 1.png 贴纸表 7 只小鱼（tools/extract_sheet_fish.py 抠出，≈460px 高）→
    happy(fish_1) / laugh(fish_4) / talk(fish_0) / think(fish_6) / sleep(fish_5) /
    surprise(fish_2) / sad(fish_0) / love(fish_1) / wave(fish_2) / eat(fish_3) /
    angry(fish_3 愤怒版)
  - 4.jpg 方形蓝角色（720×720）→ angry_alt（愤怒时与 fish_3 各 50% 出现）
  - 2.png / 3.png → talk / think 帧里的圆角"小照片"点缀（背景复杂无法作主体）

输出：assets/mascot/master/{state}_{i}.png（含 angryalt_*，共 40 帧）
联络表：docs/screenshots/mascot_preview.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_sources import flood_remove_bg  # noqa: E402

DESKTOP = Path(r"C:\Users\38495\Desktop")
ANALYSIS = ROOT / "qa" / "out" / "mascot_analysis"
SHEET = ANALYSIS / "sheet_fish"
MASTER = ROOT / "assets" / "mascot" / "master"
CANVAS = 512
MARGIN_TOP = 46
BODY_H = CANVAS - MARGIN_TOP

EYE = dict(fx=0.345, fy=0.150, r=0.028)  # 5.png 主体可见左眼（3/4 侧视）


def load_subject5() -> Image.Image:
    im = Image.open(DESKTOP / "5.png")
    rgba, _ = flood_remove_bg(im)
    bbox = rgba.getchannel("A").getbbox()
    if bbox:
        rgba = rgba.crop(bbox)
    rgba = rgba.filter(ImageFilter.UnsharpMask(radius=2.2, percent=90, threshold=2))
    rgba = ImageEnhance.Color(rgba).enhance(1.10)
    rgba = ImageEnhance.Contrast(rgba).enhance(1.04)
    return rgba


def load_four() -> Image.Image:
    im = Image.open(DESKTOP / "4.jpg")
    rgba, _ = flood_remove_bg(im)
    bbox = rgba.getchannel("A").getbbox()
    if bbox:
        rgba = rgba.crop(bbox)
    rgba = rgba.filter(ImageFilter.UnsharpMask(radius=2.0, percent=90, threshold=2))
    return rgba


def load_sheet_fish(idx: int) -> Image.Image:
    return Image.open(SHEET / f"fish_{idx}.png").convert("RGBA")


def mini_photo(src: str, side: int = 340) -> Image.Image:
    im = Image.open(DESKTOP / src).convert("RGB")
    w, h = im.size
    left, top = (w - side) // 2, (h - side) // 3
    crop = im.crop((left, top, left + side, top + side)).resize((180, 180), Image.LANCZOS)
    mask = Image.new("L", (720, 720), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 719, 719), radius=120, fill=255)
    mask = mask.resize((180, 180), Image.LANCZOS)
    out = crop.convert("RGBA")
    out.putalpha(mask)
    border = Image.new("RGBA", (188, 188), (255, 255, 255, 255))
    bm = Image.new("L", (736, 736), 0)
    ImageDraw.Draw(bm).rounded_rectangle((0, 0, 735, 735), radius=124, fill=255)
    border.putalpha(bm.resize((188, 188), Image.LANCZOS))
    border.alpha_composite(out, (4, 4))
    return border.rotate(-6, expand=True, resample=Image.BICUBIC)


COL = {
    "heart": (255, 90, 121, 255),
    "zz": (91, 124, 250, 255),
    "question": (61, 74, 102, 255),
    "exclaim": (229, 72, 77, 255),
    "tear": (111, 168, 255, 255),
    "anger": (229, 72, 77, 255),
    "sparkle": (255, 197, 61, 255),
    "note": (139, 92, 246, 255),
    "speed": (154, 167, 199, 255),
    "wave": (120, 145, 200, 255),
    "crumb": (244, 162, 97, 255),
    "dot": (90, 106, 140, 255),
}


def face_color_near(body: Image.Image, eye: dict) -> tuple[int, int, int]:
    w, h = body.size
    cx, cy = int(eye["fx"] * w), int(eye["fy"] * h)
    r = max(6, int(eye["r"] * w * 2.4))
    px = body.convert("RGB").load()
    ring = []
    for dx in range(-r, r + 1, 2):
        for dy in (-r, r):
            x, y = cx + dx, cy + dy
            if 0 <= x < w and 0 <= y < h:
                ring.append(px[x, y])
    if not ring:
        return (250, 250, 250)
    n = len(ring)
    return (sum(p[0] for p in ring) // n, sum(p[1] for p in ring) // n, sum(p[2] for p in ring) // n)


def draw_heart(d: ImageDraw.ImageDraw, cx: int, cy: int, s: int, fill) -> None:
    import math
    pts = []
    for i in range(26):
        a = math.tau * i / 26
        x = 16 * math.sin(a) ** 3
        y = -(13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a))
        pts.append((cx + x * s / 16, cy + y * s / 16))
    d.polygon(pts, fill=fill)


def draw_symbol(layer: Image.Image, kind: str, n: int) -> None:
    d = ImageDraw.Draw(layer)
    W, H = layer.size
    if kind == "heart":
        spots = [(int(W * 0.80), int(H * 0.16), 30), (int(W * 0.88), int(H * 0.30), 20), (int(W * 0.72), int(H * 0.34), 15)]
        for cx, cy, s in spots[: max(1, n)]:
            draw_heart(d, cx, cy, s, COL["heart"])
    elif kind == "zz":
        from PIL import ImageFont
        for i in range(n):
            size = 44 - i * 10
            f2 = _font(size)
            d.text((W * 0.74 + i * 26, H * 0.10 + i * 34), "Z", font=f2, fill=COL["zz"])
    elif kind == "question":
        d.text((W * 0.78, H * 0.10), "?", font=_font(52), fill=COL["question"])
        if n > 1:
            d.text((W * 0.86, H * 0.22), "?", font=_font(30), fill=COL["question"])
    elif kind == "exclaim":
        d.text((W * 0.80, H * 0.08), "!", font=_font(56), fill=COL["exclaim"])
    elif kind == "tear":
        for i in range(n + 1):
            cx, cy, s = int(W * (0.40 + i * 0.10)), int(H * (0.30 + i * 0.05)), 16 - i * 3
            d.ellipse((cx - s, cy - s, cx + s, cy + s), fill=COL["tear"])
            d.polygon([(cx - s, cy + s // 2), (cx, cy - s * 2), (cx + s, cy + s // 2)], fill=COL["tear"])
    elif kind == "anger":
        import math
        cx, cy, s = int(W * 0.76), int(H * 0.14), 26
        for a in (15, 75, 165, 255):
            rad = math.radians(a)
            x2, y2 = cx + s * math.cos(rad), cy - s * math.sin(rad)
            d.line((cx - x2 + cx, cy - y2 + cy, x2, y2), fill=COL["anger"], width=9)
    elif kind == "sparkle":
        spots = [(int(W * 0.80), int(H * 0.14), 26), (int(W * 0.88), int(H * 0.28), 16), (int(W * 0.70), int(H * 0.30), 12)]
        for cx, cy, s in spots[: max(1, n)]:
            d.polygon([(cx, cy - s), (cx + s * 0.3, cy - s * 0.3), (cx + s, cy), (cx + s * 0.3, cy + s * 0.3),
                       (cx, cy + s), (cx - s * 0.3, cy + s * 0.3), (cx - s, cy), (cx - s * 0.3, cy - s * 0.3)],
                      fill=COL["sparkle"])
    elif kind == "note":
        d.ellipse((W * 0.78, H * 0.22, W * 0.78 + 18, H * 0.22 + 14), fill=COL["note"])
        d.line((W * 0.78 + 16, H * 0.22, W * 0.78 + 16, H * 0.10), fill=COL["note"], width=5)
        d.line((W * 0.78 + 16, H * 0.10, W * 0.78 + 34, H * 0.15), fill=COL["note"], width=5)
        if n > 1:
            d.ellipse((W * 0.86, H * 0.34, W * 0.86 + 14, H * 0.34 + 11), fill=COL["note"])
            d.line((W * 0.86 + 12, H * 0.34, W * 0.86 + 12, H * 0.24), fill=COL["note"], width=4)
    elif kind == "speed":
        for i in range(3):
            y = H * (0.30 + i * 0.16)
            d.line((W * 0.10, y, W * 0.30, y), fill=COL["speed"], width=8)
            d.line((W * 0.16, y + H * 0.05, W * 0.34, y + H * 0.05), fill=(*COL["speed"][:3], 160), width=5)
    elif kind == "wave":
        import math
        cx, cy = W * 0.82, H * 0.16
        pts = [(cx + i * 6, cy + (10 if i % 2 else -10)) for i in range(9)]
        d.line(pts, fill=COL["wave"], width=6, joint="curve")
    elif kind == "crumb":
        for i in range(4):
            cx, cy = W * (0.46 + (i % 2) * 0.07 - 0.02), H * (0.28 + (i // 2) * 0.05)
            s = 7 - i
            d.ellipse((cx - s, cy - s, cx + s, cy + s), fill=COL["crumb"])
    elif kind == "dot":
        for i in range(n):
            s = 7
            cx, cy = W * (0.55 + i * 0.05), H * (0.20 + i * 0.015)
            d.ellipse((cx - s, cy - s, cx + s, cy + s), fill=COL["dot"])


_FONT_CACHE: dict[int, object] = {}


def _font(size: int):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    from PIL import ImageFont
    f = None
    for name in ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf", "segoeui.ttf"):
        p = Path("C:/Windows/Fonts") / name
        if p.exists():
            f = ImageFont.truetype(str(p), size)
            break
    if f is None:
        f = ImageFont.load_default()
    _FONT_CACHE[size] = f
    return f


def compose(body: Image.Image, spec: dict, minis: dict[str, Image.Image] | None = None) -> Image.Image:
    squash, rot, dx, dy = spec["t"]
    th = int(BODY_H * squash)
    tw = int(body.width * th / body.height)
    img = body.resize((tw, th), Image.LANCZOS)
    if rot:
        img = img.rotate(rot, expand=True, resample=Image.BICUBIC)
    if spec.get("dark"):
        img = ImageEnhance.Brightness(img).enhance(spec["dark"])
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    bx = (CANVAS - img.width) // 2 + dx
    by = CANVAS - img.height + dy
    canvas.alpha_composite(img, (bx, by))
    lid = spec.get("lid")
    if lid and body is BODIES.get("subject5"):
        overlay = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        ex = bx + EYE["fx"] * img.width
        ey = by + EYE["fy"] * img.height
        er = max(5, EYE["r"] * img.width * 1.6)
        color = face_color_near(body, EYE)
        hh = er * 1.15 * lid
        od.ellipse((ex - er * 1.05, ey - hh, ex + er * 1.05, ey + hh), fill=(*color, 255))
        od.arc((ex - er, ey - er * 0.5, ex + er, ey + er * 1.1), start=15, end=165,
               fill=(45, 55, 85, 255), width=max(2, int(er * 0.22)))
        canvas.alpha_composite(overlay)
    if spec.get("sym"):
        sym = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        draw_symbol(sym, spec["sym"], spec.get("n", 1))
        canvas.alpha_composite(sym)
    if spec.get("mini") and minis:
        photo = minis[spec["mini"]]
        canvas.alpha_composite(photo, (int(CANVAS * 0.06), int(CANVAS * 0.60)))
    return canvas


# 状态帧表：body = 素材键；t=(squash_y, rotate, dx, dy)
FRAMES: dict[str, list[dict]] = {
    "idle": [
        dict(body="subject5", t=(1.00, 0, 0, 0)),
        dict(body="subject5", t=(0.97, 0, 0, 2)),
        dict(body="subject5", t=(0.94, 0, 0, 4)),
        dict(body="subject5", t=(0.97, 0, 0, 2)),
    ],
    "blink": [
        dict(body="subject5", t=(1.00, 0, 0, 0), lid=0.0),
        dict(body="subject5", t=(0.985, 0, 0, 1), lid=0.6),
        dict(body="subject5", t=(0.97, 0, 0, 2), lid=1.0),
    ],
    "happy": [
        dict(body="fish_1", t=(1.00, -3, 0, 0), sym="sparkle", n=1),
        dict(body="fish_1", t=(0.93, 3, 0, 3), sym="sparkle", n=3),
        dict(body="fish_1", t=(0.96, -2, 0, 1), sym="sparkle", n=2),
    ],
    "laugh": [
        dict(body="fish_4", t=(1.02, -4, 0, -2), sym="note", n=1),
        dict(body="fish_4", t=(0.90, 5, 0, 5), sym="note", n=2),
        dict(body="fish_4", t=(0.95, 0, 0, 2), sym="note", n=1),
    ],
    "talk": [
        dict(body="fish_0", t=(1.00, 0, 0, 0)),
        dict(body="fish_0", t=(0.96, 2, 1, 3), sym="dot", n=1),
        dict(body="fish_0", t=(0.98, -2, -1, 1), sym="dot", n=2, mini="two"),
    ],
    "think": [
        dict(body="fish_6", t=(1.00, 4, 2, 0)),
        dict(body="fish_6", t=(0.98, 5, 3, 1), sym="question", n=1),
        dict(body="fish_6", t=(0.99, 3, 2, 0), sym="question", n=1, mini="three"),
    ],
    "sleep": [
        dict(body="fish_5", t=(0.96, 6, 3, 2), sym="zz", n=1, dark=0.94),
        dict(body="fish_5", t=(0.93, 7, 4, 4), sym="zz", n=2, dark=0.90),
        dict(body="fish_5", t=(0.95, 6, 3, 3), sym="zz", n=3, dark=0.92),
    ],
    "surprise": [
        dict(body="fish_2", t=(1.05, 0, 0, -3)),
        dict(body="fish_2", t=(1.07, 0, 0, -4), sym="exclaim", n=1),
    ],
    "sad": [
        dict(body="fish_0", t=(0.97, -5, -2, 2)),
        dict(body="fish_0", t=(0.95, -6, -3, 3), sym="tear", n=1),
    ],
    "angry": [
        dict(body="fish_3", t=(1.00, -2, -3, 0)),
        dict(body="fish_3", t=(1.00, 2, 3, 0), sym="anger", n=1),
    ],
    "angry_alt": [
        dict(body="four", t=(1.00, -2, -3, 0)),
        dict(body="four", t=(1.00, 2, 3, 0), sym="anger", n=1),
    ],
    "love": [
        dict(body="fish_1", t=(1.00, 0, 0, 0), sym="heart", n=2),
        dict(body="fish_1", t=(0.94, 0, 0, 4), sym="heart", n=3),
    ],
    "drag": [
        dict(body="subject5", t=(0.98, 12, 4, 0), sym="speed", n=1),
        dict(body="subject5", t=(0.98, 14, 6, 0), sym="speed", n=2),
    ],
    "wave": [
        dict(body="fish_2", t=(0.98, -8, 0, 0)),
        dict(body="fish_2", t=(0.98, 8, 0, 0), sym="wave", n=1),
        dict(body="fish_2", t=(0.98, -6, 0, 0)),
    ],
    "eat": [
        dict(body="fish_3", t=(1.00, 0, 0, 0)),
        dict(body="fish_3", t=(0.95, 2, 0, 4), sym="crumb", n=1),
        dict(body="fish_3", t=(0.97, -1, 0, 2), sym="crumb", n=2),
    ],
}

BODIES: dict[str, Image.Image] = {}


def load_bodies() -> None:
    BODIES["subject5"] = load_subject5()
    BODIES["four"] = load_four()
    for i in range(7):
        p = SHEET / f"fish_{i}.png"
        if p.exists():
            BODIES[f"fish_{i}"] = Image.open(p).convert("RGBA")
    print("bodies:", {k: v.size for k, v in sorted(BODIES.items())})


def contact_sheet(paths: dict[str, list[Path]], out: Path) -> None:
    cols, cell, pad = 5, 150, 10
    states = sorted(paths)
    rows = (len(states) + cols - 1) // cols
    W = cols * cell + (cols + 1) * pad
    H = rows * (cell + 26) + (rows + 1) * pad
    sheet = Image.new("RGB", (W, H), (247, 249, 255))
    d = ImageDraw.Draw(sheet)
    for i, state in enumerate(states):
        r, c = divmod(i, cols)
        x = pad + c * (cell + pad)
        y = pad + r * (cell + 26 + pad)
        frames = paths[state]
        frame = frames[len(frames) // 2] if len(frames) > 1 else frames[0]
        im = Image.open(frame).convert("RGBA")
        im.thumbnail((cell, cell), Image.LANCZOS)
        bg = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
        bg.paste(im, ((cell - im.width) // 2, (cell - im.height) // 2), im)
        sheet.paste(bg, (x, y), bg)
        d.text((x + cell // 2 - 14, y + cell + 4), state, font=_font(15), fill=(40, 50, 80))
    sheet.save(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-sheet", action="store_true", help="跳过 1.png 小鱼重抠（复用 sheet_fish/）")
    args = ap.parse_args()
    if not args.skip_sheet:
        import extract_sheet_fish
        extract_sheet_fish.main()
    load_bodies()
    minis = {"two": mini_photo("2.png"), "three": mini_photo("3.png")}
    MASTER.mkdir(parents=True, exist_ok=True)
    out_paths: dict[str, list[Path]] = {}
    total = 0
    for state, specs in FRAMES.items():
        out_paths[state] = []
        base = "angryalt" if state == "angry_alt" else state  # 与 manifest 帧名一致
        for i, spec in enumerate(specs):
            frame = compose(BODIES[spec["body"]], spec, minis)
            p = MASTER / f"{base}_{i}.png"
            frame.save(p)
            out_paths[state].append(p)
            total += 1
    print(f"frames written: {total}")
    contact_sheet(out_paths, ROOT / "docs" / "screenshots" / "mascot_preview.png")
    print("contact sheet: docs/screenshots/mascot_preview.png")


if __name__ == "__main__":
    main()
