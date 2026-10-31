# -*- coding: utf-8 -*-
"""用桌面 5.png 的蓝色大肥鱼生成桌宠全部 14 状态 × 38 帧精灵。

- 主体：5.png 洪泛抠图 → 最大连通域（685×1257 蓝头白肚肥鱼）
- 状态：整体形变（呼吸压扁/摇摆/旋转/位移）+ 矢量符号叠加（爱心/Zz/?/!/
  泪滴/青筋/音符/速度线/食物碎屑），眼睛区域检测后可画眼睑（眨眼/睡觉）
- 输出：assets/mascot/master/{state}_{i}.png（512×512 RGBA，透明底）
  + docs/screenshots/mascot_preview.png 联络表（供人工确认）
- 复现：py tools/gen_mascot_images.py [--source 5.png] [--no-eyelid]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_sources import flood_remove_bg  # noqa: E402

DESKTOP = Path(r"C:\Users\38495\Desktop")
MASTER = ROOT / "assets" / "mascot" / "master"
CANVAS = 512
MARGIN_TOP = 46          # 顶部留给符号
BODY_H = CANVAS - MARGIN_TOP

# 状态帧表： (squash_y, rotate, dx, dy) + 符号
FRAMES: dict[str, list[dict]] = {
    "idle": [
        dict(t=(1.00, 0, 0, 0)),
        dict(t=(0.97, 0, 0, 2)),
        dict(t=(0.94, 0, 0, 4)),
        dict(t=(0.97, 0, 0, 2)),
    ],
    "blink": [
        dict(t=(1.00, 0, 0, 0), lid=0.0),
        dict(t=(0.985, 0, 0, 1), lid=0.6),
        dict(t=(0.97, 0, 0, 2), lid=1.0),
    ],
    "happy": [
        dict(t=(1.00, -3, 0, 0), sym="sparkle", n=1),
        dict(t=(0.93, 3, 0, 3), sym="sparkle", n=3),
        dict(t=(0.96, -2, 0, 1), sym="sparkle", n=2),
    ],
    "laugh": [
        dict(t=(1.02, -4, 0, -2), sym="note", n=1),
        dict(t=(0.90, 5, 0, 5), sym="note", n=2),
        dict(t=(0.95, 0, 0, 2), sym="note", n=1),
    ],
    "talk": [
        dict(t=(1.00, 0, 0, 0)),
        dict(t=(0.96, 2, 1, 3), sym="dot", n=1),
        dict(t=(0.98, -2, -1, 1), sym="dot", n=2),
    ],
    "think": [
        dict(t=(1.00, 4, 2, 0)),
        dict(t=(0.98, 5, 3, 1), sym="question", n=1),
        dict(t=(0.99, 3, 2, 0), sym="question", n=1),
    ],
    "sleep": [
        dict(t=(0.96, 6, 3, 2), lid=1.0, sym="zz", n=1, dark=0.94),
        dict(t=(0.93, 7, 4, 4), lid=1.0, sym="zz", n=2, dark=0.90),
        dict(t=(0.95, 6, 3, 3), lid=1.0, sym="zz", n=3, dark=0.92),
    ],
    "surprise": [
        dict(t=(1.05, 0, 0, -3)),
        dict(t=(1.07, 0, 0, -4), sym="exclaim", n=1),
    ],
    "sad": [
        dict(t=(0.97, -5, -2, 2)),
        dict(t=(0.95, -6, -3, 3), sym="tear", n=1),
    ],
    "angry": [
        dict(t=(1.00, -2, -3, 0)),
        dict(t=(1.00, 2, 3, 0), sym="anger", n=1),
    ],
    "love": [
        dict(t=(1.00, 0, 0, 0), sym="heart", n=2),
        dict(t=(0.94, 0, 0, 4), sym="heart", n=3),
    ],
    "drag": [
        dict(t=(0.98, 12, 4, 0), sym="speed", n=1),
        dict(t=(0.98, 14, 6, 0), sym="speed", n=2),
    ],
    "wave": [
        dict(t=(0.98, -8, 0, 0)),
        dict(t=(0.98, 8, 0, 0), sym="wave", n=1),
        dict(t=(0.98, -6, 0, 0)),
    ],
    "eat": [
        dict(t=(1.00, 0, 0, 0)),
        dict(t=(0.95, 2, 0, 4), sym="crumb", n=1),
        dict(t=(0.97, -1, 0, 2), sym="crumb", n=2),
    ],
}

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


def load_subject(source: str) -> Image.Image:
    im = Image.open(DESKTOP / source)
    rgba, _ = flood_remove_bg(im)
    # 最大连通域裁剪
    alpha = rgba.getchannel("A")
    bbox = alpha.getbbox()
    if bbox:
        rgba = rgba.crop(bbox)
    # 轻度锐化+增饱和，让照片主体更"卡通干净"
    rgba = rgba.filter(ImageFilter.UnsharpMask(radius=2.2, percent=90, threshold=2))
    rgba = ImageEnhance.Color(rgba).enhance(1.10)
    rgba = ImageEnhance.Contrast(rgba).enhance(1.04)
    return rgba


def find_eyes(subject: Image.Image) -> list[dict]:
    """5.png 主体为 3/4 侧视：仅左眼清晰可见（深色簇 fx≈0.345, fy≈0.150），
    右眼被头鳍遮挡。眨眼做单眼 wink。"""
    return [dict(fx=0.345, fy=0.150, r=0.028)]


def face_color_near(subject: Image.Image, eye: dict) -> tuple[int, int, int]:
    """取眼睛周围一圈的肤色（画眼睑用）。"""
    w, h = subject.size
    cx, cy = int(eye["fx"] * w), int(eye["fy"] * h)
    r = max(6, int(eye["r"] * w * 2.4))
    ring = []
    px = subject.convert("RGB").load()
    for dx in range(-r, r + 1, 2):
        for dy in (-r, r):
            x, y = cx + dx, cy + dy
            if 0 <= x < w and 0 <= y < h:
                ring.append(px[x, y])
    if not ring:
        return (250, 250, 250)
    n = len(ring)
    return (sum(p[0] for p in ring) // n, sum(p[1] for p in ring) // n, sum(p[2] for p in ring) // n)


def font_for(size: int) -> ImageFont.ImageFont:
    for name in ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf", "segoeui.ttf"):
        p = Path("C:/Windows/Fonts") / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def draw_heart(d: ImageDraw.ImageDraw, cx: int, cy: int, s: int, fill) -> None:
    pts = []
    import math
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
        f = font_for(44)
        for i in range(n):
            size = 44 - i * 10
            f2 = font_for(size) if size != 44 else f
            d.text((W * 0.74 + i * 26, H * 0.10 + i * 34), "Z", font=f2, fill=COL["zz"])
    elif kind == "question":
        f = font_for(52)
        d.text((W * 0.78, H * 0.10), "?", font=f, fill=COL["question"])
        if n > 1:
            d.text((W * 0.86, H * 0.22), "?", font=font_for(30), fill=COL["question"])
    elif kind == "exclaim":
        f = font_for(56)
        d.text((W * 0.80), 0, "", font=f, fill=COL["exclaim"]) if False else None
        d.text((W * 0.80, H * 0.08), "!", font=f, fill=COL["exclaim"])
    elif kind == "tear":
        for i in range(n + 1):
            cx, cy, s = int(W * (0.40 + i * 0.10)), int(H * (0.30 + i * 0.05)), 16 - i * 3
            d.ellipse((cx - s, cy - s, cx + s, cy + s), fill=COL["tear"])
            d.polygon([(cx - s, cy + s // 2), (cx, cy - s * 2), (cx + s, cy + s // 2)], fill=COL["tear"])
    elif kind == "anger":
        cx, cy, s = int(W * 0.76), int(H * 0.14), 26
        for a in (15, 75, 165, 255):
            import math
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
        # 嘴部 (≈0.46, 0.19 主体相对) 下落的食物碎屑
        for i in range(4):
            cx, cy = W * (0.46 + (i % 2) * 0.07 - 0.02), H * (0.28 + (i // 2) * 0.05)
            s = 7 - i
            d.ellipse((cx - s, cy - s, cx + s, cy + s), fill=COL["crumb"])
    elif kind == "dot":
        # 嘴右侧的说话气泡点
        for i in range(n):
            s = 7
            cx, cy = W * (0.55 + i * 0.05), H * (0.20 + i * 0.015)
            d.ellipse((cx - s, cy - s, cx + s, cy + s), fill=COL["dot"])


def compose_frame(subject: Image.Image, spec: dict, eyes: list[dict], use_eyelid: bool) -> Image.Image:
    squash, rot, dx, dy = spec["t"]
    # 目标：主体高 = BODY_H（squash 围绕底部锚点）
    th = int(BODY_H * squash)
    tw = int(subject.width * th / subject.height)
    body = subject.resize((tw, th), Image.LANCZOS)
    if rot:
        body = body.rotate(rot, expand=True, resample=Image.BICUBIC)
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    bx = (CANVAS - body.width) // 2 + dx
    by = CANVAS - body.height + dy
    dark = spec.get("dark")
    if dark:
        body = ImageEnhance.Brightness(body).enhance(dark)
    canvas.alpha_composite(body, (bx, by))
    # 眼睑（单眼 wink：白色覆盖 + 下弯闭眼弧线）
    lid = spec.get("lid")
    if lid and use_eyelid and eyes:
        overlay = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for e in eyes:
            ex = bx + e["fx"] * body.width
            ey = by + e["fy"] * body.height
            er = max(5, e["r"] * body.width * 1.6)
            color = face_color_near(subject, e)
            hh = er * 1.15 * lid
            od.ellipse((ex - er * 1.05, ey - hh, ex + er * 1.05, ey + hh), fill=(*color, 255))
            # 闭眼弧线（向下弯）
            lw = max(2, int(er * 0.22))
            od.arc((ex - er, ey - er * 0.5, ex + er, ey + er * 1.1), start=15, end=165, fill=(45, 55, 85, 255), width=lw)
        canvas.alpha_composite(overlay)
    # 符号
    if spec.get("sym"):
        sym_layer = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        draw_symbol(sym_layer, spec["sym"], spec.get("n", 1))
        canvas.alpha_composite(sym_layer)
    return canvas


def contact_sheet(paths: dict[str, list[Path]], out: Path) -> None:
    cols, cell, pad = 7, 150, 10
    rows = 2
    W = cols * cell + (cols + 1) * pad
    H = rows * (cell + 26) + (rows + 1) * pad
    sheet = Image.new("RGB", (W, H), (247, 249, 255))
    d = ImageDraw.Draw(sheet)
    f = font_for(15)
    for i, (state, frames) in enumerate(sorted(paths.items())):
        r, c = divmod(i, cols)
        x = pad + c * (cell + pad)
        y = pad + r * (cell + 26 + pad)
        frame = frames[len(frames) // 2] if len(frames) > 1 else frames[0]
        im = Image.open(frame).convert("RGBA")
        im.thumbnail((cell, cell), Image.LANCZOS)
        bg = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
        bg.paste(im, ((cell - im.width) // 2, (cell - im.height) // 2), im)
        sheet.paste(bg, (x, y), bg)
        d.text((x + cell // 2 - 14, y + cell + 4), state, font=f, fill=(40, 50, 80))
    sheet.save(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="5.png")
    ap.add_argument("--no-eyelid", action="store_true")
    args = ap.parse_args()

    subject = load_subject(args.source)
    print(f"subject: {subject.size}")
    eyes = find_eyes(subject)
    print(f"eyes: {[(round(e['fx'],2), round(e['fy'],2), round(e['r'],3)) for e in eyes]}")

    MASTER.mkdir(parents=True, exist_ok=True)
    out_paths: dict[str, list[Path]] = {}
    total = 0
    for state, specs in FRAMES.items():
        out_paths[state] = []
        for i, spec in enumerate(specs):
            frame = compose_frame(subject, spec, eyes, not args.no_eyelid)
            p = MASTER / f"{state}_{i}.png"
            frame.save(p)
            out_paths[state].append(p)
            total += 1
    print(f"frames written: {total}")
    sheet = ROOT / "docs" / "screenshots" / "mascot_preview.png"
    contact_sheet(out_paths, sheet)
    print(f"contact sheet: {sheet}")


if __name__ == "__main__":
    main()
