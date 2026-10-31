# -*- coding: utf-8 -*-
"""彩色字母 ASCII 预览：按色相把像素映射为颜色字母，用于人/模型阅读图内容。"""
from __future__ import annotations

import colorsys
import sys
from pathlib import Path

from PIL import Image

CH_W = 96


def color_char(r: int, g: int, b: int, a: int) -> str:
    if a < 90:
        return " "
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    hd = h * 360
    if v < 0.16:
        return "K"
    if s < 0.14:
        return "W" if v > 0.72 else "w"
    if hd < 20 or hd > 330:
        return "R"
    if hd < 45:
        return "O"
    if hd < 70:
        return "Y"
    if hd < 160:
        return "G"
    if hd < 200:
        return "C"
    if hd < 260:
        return "B"
    return "P"


def preview(path: Path, width: int = CH_W) -> str:
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    nh = max(1, int(width * h / w * 0.45))
    im = im.resize((width, nh), Image.BILINEAR)
    px = im.load()
    lines = [f"--- {path.name} {w}x{h}"]
    for y in range(nh):
        lines.append("".join(color_char(*px[x, y]) for x in range(width)))
    return "\n".join(lines)


def main() -> None:
    OUT = Path(__file__).resolve().parent.parent / "qa" / "out" / "mascot_analysis"
    targets = [
        OUT / "1_cut.png", OUT / "4_comp0.png", OUT / "5_comp0.png",
        OUT / "2_comp0.png", OUT / "3_cut.png",
        OUT.parent.parent.parent / "qa" / "out" / "icon_candidates" / "candidate_1.png",
        OUT.parent.parent.parent / "qa" / "out" / "icon_candidates" / "candidate_5.png",
    ]
    parts = []
    for t in targets:
        if t.exists():
            parts.append(preview(t))
        else:
            parts.append(f"--- {t.name} MISSING")
    text = "\n\n".join(parts)
    (OUT / "color_ascii.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
