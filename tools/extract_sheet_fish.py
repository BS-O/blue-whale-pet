# -*- coding: utf-8 -*-
"""抠出 1.png 贴纸表全部小鱼并逐只 ASCII 预览 + 保存。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_sources import flood_remove_bg  # noqa: E402
from color_ascii import preview  # noqa: E402

DESKTOP = Path(r"C:\Users\38495\Desktop")
OUT = Path(__file__).resolve().parent.parent / "qa" / "out" / "mascot_analysis" / "sheet_fish"
OUT.mkdir(parents=True, exist_ok=True)


def components_on_alpha(rgba: Image.Image, min_px: int = 400):
    w, h = rgba.size
    scale = min(1.0, 800.0 / max(w, h))
    small = rgba.resize((int(w * scale), int(h * scale)), Image.BILINEAR)
    sw, sh = small.size
    ap = small.getchannel("A").load()
    from collections import deque
    visited = bytearray(sw * sh)
    comps = []
    for sy in range(sh):
        for sx in range(sw):
            if visited[sy * sw + sx] or ap[sx, sy] < 96:
                continue
            dq = deque([(sx, sy)])
            visited[sy * sw + sx] = 1
            minx = maxx = sx; miny = maxy = sy; area = 0
            while dq:
                x, y = dq.popleft(); area += 1
                minx = min(minx, x); maxx = max(maxx, x)
                miny = min(miny, y); maxy = max(maxy, y)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < sw and 0 <= ny < sh and not visited[ny * sw + nx] and ap[nx, ny] >= 96:
                        visited[ny * sw + nx] = 1
                        dq.append((nx, ny))
            if area >= min_px * scale * scale:
                comps.append((minx, miny, maxx, maxy, area))
    comps.sort(key=lambda c: -c[4])
    return comps, scale


def main() -> None:
    im = Image.open(DESKTOP / "1.png")
    rgba, ratio = flood_remove_bg(im)
    comps, scale = components_on_alpha(rgba, min_px=3000)
    print(f"cut {ratio:.0%}, comps: {len(comps)}")
    for i, (x0, y0, x1, y1, area) in enumerate(comps[:14]):
        pad = 4
        crop = rgba.crop((max(0, x0 - pad), max(0, y0 - pad), min(rgba.width, x1 + pad), min(rgba.height, y1 + pad)))
        # 放大到高度 ~460（LANCZOS + 锐化），供精灵用
        target_h = 460
        scale_up = target_h / crop.height
        up = crop.resize((int(crop.width * scale_up), target_h), Image.LANCZOS)
        up = up.filter(ImageFilter.UnsharpMask(radius=2.0, percent=110, threshold=2))
        up = ImageEnhance.Color(up).enhance(1.10)
        up.save(OUT / f"fish_{i}.png")
        pw = int(crop.width * scale_up)
        print(f"\n### fish_{i}  src=({x1-x0}x{y1-y0}) area={area}")
        print(preview(OUT / f"fish_{i}.png", 52))


if __name__ == "__main__":
    main()
