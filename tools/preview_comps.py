# -*- coding: utf-8 -*-
"""对分析输出目录里所有组件裁剪生成 ASCII 轮廓 + 汇总信息。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_sources import ascii_preview, hsv_stats  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "qa" / "out" / "mascot_analysis"

RAMP = " .:-=+*#%@"


def prev_of(p: Path, width: int = 44) -> str:
    im = Image.open(p).convert("RGBA")
    return ascii_preview(im, width)


def main() -> None:
    files = sorted(OUT.glob("*_comp*.png"))
    report = []
    for p in files:
        im = Image.open(p).convert("RGBA")
        hue, sat, val = hsv_stats(im)
        report.append(f"\n### {p.name}  {im.size}  hsv=({hue:.0f},{sat:.2f},{val:.2f})\n{prev_of(p)}")
    txt = "\n".join(report)
    (OUT / "all_comps_preview.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
