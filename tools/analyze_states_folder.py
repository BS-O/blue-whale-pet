# -*- coding: utf-8 -*-
"""分析"1"文件夹状态图 + icon/ico.png：尺寸/背景/抠图/轮廓预览。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_sources import flood_remove_bg, border_bg_color  # noqa: E402
from color_ascii import preview  # noqa: E402

from PIL import Image

DESK1 = Path(r"C:\Users\38495\Desktop\1")
ICON = Path(r"C:\Users\38495\Desktop\icon\ico.png")
OUT = Path(__file__).resolve().parent.parent / "qa" / "out" / "mascot_analysis" / "states"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    files = sorted(DESK1.glob("*.png")) + [DESK1 / "4.jpg"] + [ICON]
    for p in files:
        if not p.exists():
            continue
        im = Image.open(p)
        print(f"\n===== {p.name}: {im.size} mode={im.mode}")
        rgba, ratio = flood_remove_bg(im)
        bg = border_bg_color(im.convert("RGB"))
        print(f"bg={bg} flood_removed={ratio:.0%}")
        bbox = rgba.getchannel("A").getbbox()
        if bbox:
            rgba = rgba.crop(bbox)
            rgba = rgba.filter(__import__("PIL.ImageFilter", fromlist=["UnsharpMask"]).UnsharpMask(2.0, 90, 2))
        rgba.save(OUT / f"{p.stem}_cut.png")
        print(preview(OUT / f"{p.stem}_cut.png", 64))


if __name__ == "__main__":
    main()
