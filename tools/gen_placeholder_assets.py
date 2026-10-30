"""生成占位资产（仅用于 pet-core / pack-* 早期联调）。
asset-fish 会用真正的美术资产替换本脚本产出的内容。
用法: py tools/gen_placeholder_assets.py
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "assets"
KEY = "#010203"
BLUE = (77, 107, 254)
DARK = (11, 19, 48)
WHITE = (255, 255, 255)
CANVAS = 512

STATES = {
    "idle": 4, "blink": 3, "happy": 3, "laugh": 3, "talk": 3, "think": 3, "sleep": 3,
    "surprise": 2, "sad": 2, "angry": 2, "love": 2, "drag": 2, "wave": 3, "eat": 3,
}
DUR = {"idle": 420, "blink": 70, "happy": 200, "laugh": 140, "talk": 160, "think": 300,
       "sleep": 800, "surprise": 180, "sad": 500, "angry": 220, "love": 400, "drag": 150,
       "wave": 240, "eat": 260}


def draw_pet(state: str, frame: int, n: int) -> Image.Image:
    """极简占位蓝鲸：椭圆身体 + 尾巴 + 表情眼睛。"""
    S = 4
    im = Image.new("RGBA", (CANVAS * S, CANVAS * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = CANVAS * S // 2, 300 * S
    bob = int(math.sin(frame / max(n, 1) * math.tau) * 4 * S) if n > 1 and state in ("idle", "talk", "wave") else 0
    rx, ry = 185 * S, 135 * S
    body = [cx - rx, cy - ry + bob, cx + rx - 30 * S, cy + ry + bob]
    # 尾巴
    d.polygon([(cx + rx - 90 * S, cy - 40 * S + bob), (cx + rx + 20 * S, cy - 95 * S + bob),
               (cx + rx + 60 * S, cy - 20 * S + bob), (cx + rx - 40 * S, cy + 10 * S + bob)],
              fill=BLUE, outline=DARK, width=6 * S)
    d.ellipse(body, fill=BLUE, outline=DARK, width=8 * S)
    # 肚皮
    d.ellipse([cx - 120 * S, cy - 20 * S + bob, cx + 80 * S, cy + 115 * S + bob], fill=(96, 130, 255))
    # 眼睛
    ex, ey = cx - 55 * S, cy - 45 * S + bob
    if state in ("blink", "sleep") or (state in ("talk",) and frame % 3 == 2):
        d.line([ex - 18 * S, ey, ex + 18 * S, ey], fill=WHITE, width=7 * S)
        d.line([ex + 62 * S, ey - 6 * S, ex + 98 * S, ey - 6 * S], fill=WHITE, width=7 * S)
    elif state == "happy" or state == "laugh":
        for ox in (0, 80 * S):
            d.arc([ex + ox - 20 * S, ey - 16 * S, ex + ox + 20 * S, ey + 16 * S], 200, 340, fill=WHITE, width=7 * S)
    elif state == "love":
        for ox in (0, 80 * S):
            d.polygon([(ex + ox, ey + 12 * S), (ex + ox - 16 * S, ey - 6 * S), (ex + ox - 5 * S, ey - 20 * S),
                       (ex + ox, ey - 10 * S), (ex + ox + 5 * S, ey - 20 * S), (ex + ox + 16 * S, ey - 6 * S)],
                      fill=(255, 90, 130))
    else:
        for ox in (0, 80 * S):
            d.ellipse([ex + ox - 20 * S, ey - 26 * S, ex + ox + 20 * S, ey + 26 * S], fill=WHITE)
            d.ellipse([ex + ox - 9 * S, ey - 14 * S, ex + ox + 9 * S, ey + 14 * S], fill=DARK)
            d.ellipse([ex + ox - 3 * S, ey - 10 * S, ex + ox + 5 * S, ey - 2 * S], fill=WHITE)
    # 嘴
    mx, my = cx + 25 * S, cy + 15 * S + bob
    if state in ("happy", "laugh", "talk", "eat"):
        op = 1.0 if state in ("happy", "laugh") else (0.4 + 0.6 * (frame % 2))
        d.chord([mx - 22 * S, my - 10 * S, mx + 22 * S, my + 36 * S * op], 0, 180, fill=(190, 40, 70), outline=DARK, width=4 * S)
    elif state in ("sad", "angry", "surprise"):
        d.arc([mx - 18 * S, my, mx + 18 * S, my + 30 * S], 200, 340, fill=DARK, width=6 * S)
    else:
        d.arc([mx - 20 * S, my - 6 * S, mx + 20 * S, my + 16 * S], 20, 160, fill=DARK, width=5 * S)
    # 腮红
    for ox in (-120 * S, 130 * S):
        d.ellipse([cx + ox - 20 * S, cy + 5 * S + bob, cx + ox + 20 * S, cy + 30 * S + bob], fill=(255, 130, 160, 90))
    if state == "think":
        d.ellipse([cx + 60 * S, cy - 150 * S, cx + 90 * S, cy - 120 * S], fill=WHITE, outline=DARK, width=4 * S)
        d.ellipse([cx + 95 * S, cy - 175 * S, cx + 135 * S, cy - 135 * S], fill=WHITE, outline=DARK, width=4 * S)
    if state == "sleep":
        d.text((cx + 90 * S, cy - 170 * S), "Z", fill=(150, 180, 255))
    if state == "surprise":
        d.ellipse([mx - 10 * S, my, mx + 10 * S, my + 20 * S], fill=(120, 30, 60), outline=DARK, width=3 * S)
    return im.resize((CANVAS, CANVAS), Image.LANCZOS)


def main() -> None:
    (A / "mascot" / "master").mkdir(parents=True, exist_ok=True)
    (A / "icons" / "hicolor").mkdir(parents=True, exist_ok=True)
    (A / "installer").mkdir(parents=True, exist_ok=True)
    (A / "preview").mkdir(parents=True, exist_ok=True)
    manifest = {"version": 1,
                "canvas": {"w": CANVAS, "h": CANVAS, "anchor_x": 256, "anchor_y": 496},
                "key_color": KEY, "default_state": "idle", "states": {}}
    thumbs = []
    for state, n in STATES.items():
        names = []
        for f in range(n):
            img = draw_pet(state, f, n)
            name = f"{state}_{f}"
            img.save(A / "mascot" / "master" / f"{name}.png")
            names.append(name)
        manifest["states"][state] = {"frames": names,
                                     "durations": [DUR[state]] * n,
                                     "loop": state in ("idle", "talk", "wave", "eat")}
        thumbs.append((state, draw_pet(state, 0, n).resize((128, 128), Image.LANCZOS)))
    (A / "mascot" / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    icon = draw_pet("happy", 0, 2).resize((512, 512), Image.LANCZOS)
    icon.save(A / "icons" / "app.png")
    ico = [icon.resize((s, s), Image.LANCZOS) for s in (256, 128, 64, 48, 32, 16)]
    ico[0].save(A / "icons" / "app.ico", sizes=[(s, s) for s in (256, 128, 64, 48, 32, 16)])
    tray = icon.resize((64, 64), Image.LANCZOS)
    tray.save(A / "icons" / "tray.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    for s in (16, 24, 32, 48, 64, 128, 256, 512):
        p = A / "icons" / "hicolor" / f"{s}x{s}" / "apps"
        p.mkdir(parents=True, exist_ok=True)
        icon.resize((s, s), Image.LANCZOS).save(p / "blue-whale-pet.png")
    # 安装器占位插画
    banner = Image.new("RGBA", (600, 160), (18, 30, 80, 255))
    bd = ImageDraw.Draw(banner)
    bd.text((24, 60), "Blue Whale Pet  蓝鲸桌宠", fill=(255, 255, 255))
    p = icon.resize((120, 120), Image.LANCZOS)
    banner.alpha_composite(p, (450, 20))
    banner.save(A / "installer" / "banner.png")
    side = Image.new("RGBA", (164, 314), (18, 30, 80, 255))
    side.alpha_composite(icon.resize((150, 150), Image.LANCZOS), (7, 70))
    side.save(A / "installer" / "side.png")
    icon.save(A / "installer" / "setup.ico", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    # 预览拼图
    cols, cell = 5, 160
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * cell, rows * cell), (245, 247, 252))
    sd = ImageDraw.Draw(sheet)
    for i, (state, im) in enumerate(thumbs):
        x, y = (i % cols) * cell, (i // cols) * cell
        sheet.paste(im, (x + 16, y + 8), im)
        sd.text((x + 16, y + 138), state, fill=(30, 40, 80))
    sheet.save(A / "preview" / "contact_sheet.png")
    print("placeholder assets generated ->", A)


if __name__ == "__main__":
    main()
