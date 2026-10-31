# -*- coding: utf-8 -*-
"""分析桌面 1~5 号素材：尺寸、背景、洪泛抠图、连通域、主体候选、眼睛候选。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageFilter

DESKTOP = Path(r"C:\Users\38495\Desktop")
OUT = Path(__file__).resolve().parent.parent / "qa" / "out" / "mascot_analysis"
OUT.mkdir(parents=True, exist_ok=True)

SOURCES = ["1.png", "2.png", "3.png", "4.jpg", "5.png"]
RAMP = " .:-=+*#%@"
BLUE_H = (185.0, 255.0)


def border_bg_color(im: Image.Image) -> tuple[int, int, int]:
    w, h = im.size
    px = im.load()
    samples = []
    step = max(1, w // 40)
    for x in range(0, w, step):
        samples.append(px[x, 0]); samples.append(px[x, h - 1])
    step = max(1, h // 40)
    for y in range(0, h, step):
        samples.append(px[0, y]); samples.append(px[w - 1, y])
    rs = sorted(s[0] for s in samples); gs = sorted(s[1] for s in samples); bs = sorted(s[2] for s in samples)
    n = len(samples) // 2
    return (rs[n], gs[n], bs[n])


def flood_remove_bg(im: Image.Image, tolerance: float | None = None) -> tuple[Image.Image, float]:
    """边界洪泛把背景变透明，返回 (RGBA, 淹没比例)。"""
    rgb = im.convert("RGB")
    w, h = rgb.size
    bg = border_bg_color(rgb)
    if tolerance is None:
        uniform = 0.0
        px = rgb.load()
        cnt = tot = 0
        for x in range(0, w, max(1, w // 60)):
            for y in (0, h - 1):
                p = px[x, y]; tot += 1
                if max(abs(p[0] - bg[0]), abs(p[1] - bg[1]), abs(p[2] - bg[2])) <= 18:
                    cnt += 1
        for y in range(0, h, max(1, h // 60)):
            for x in (0, w - 1):
                p = px[x, y]; tot += 1
                if max(abs(p[0] - bg[0]), abs(p[1] - bg[1]), abs(p[2] - bg[2])) <= 18:
                    cnt += 1
        uniform = cnt / max(1, tot)
        tolerance = 26 if uniform > 0.9 else 46
    small = rgb.resize((min(w, 320), int(min(w, 320) * h / w)), Image.BILINEAR)
    from collections import deque
    sw, sh = small.size
    sp = small.load()
    visited = bytearray(sw * sh)
    dq = deque()
    for x in range(sw):
        for y in (0, sh - 1):
            if not visited[y * sw + x]:
                dq.append((x, y)); visited[y * sw + x] = 1
    for y in range(sh):
        for x in (0, sw - 1):
            if not visited[y * sw + x]:
                dq.append((x, y)); visited[y * sw + x] = 1
    tol = tolerance
    mark = bytearray(sw * sh)
    while dq:
        x, y = dq.popleft()
        p = sp[x, y]
        mark[y * sw + x] = 1
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < sw and 0 <= ny < sh and not visited[ny * sw + nx]:
                q = sp[nx, ny]
                if max(abs(q[0] - bg[0]), abs(q[1] - bg[1]), abs(q[2] - bg[2])) <= tol:
                    visited[ny * sw + nx] = 1
                    dq.append((nx, ny))
    ratio = sum(mark) / (sw * sh)
    mask_small = Image.frombytes("L", (sw, sh), bytes(255 if m == 0 else 0 for m in mark))
    mask = mask_small.resize((w, h), Image.BILINEAR)
    rgba = rgb.convert("RGBA")
    rgba.putalpha(mask)
    return rgba, ratio


def components(rgba: Image.Image, min_frac: float = 0.004):
    """alpha 二值化后 BFS 连通域，返回 [(bbox, area_frac)]（降序）。"""
    w, h = rgba.size
    small_w = min(720, w)
    small = rgba.resize((small_w, int(small_w * h / w)), Image.BILINEAR)
    sw, sh = small.size
    alpha = small.getchannel("A")
    px = alpha.load()
    visited = bytearray(sw * sh)
    comps = []
    for sy in range(sh):
        for sx in range(sw):
            if visited[sy * sw + sx] or px[sx, sy] < 96:
                continue
            from collections import deque
            dq = deque([(sx, sy)]); visited[sy * sw + sx] = 1
            minx = maxx = sx; miny = maxy = sy; area = 0
            while dq:
                x, y = dq.popleft(); area += 1
                minx = min(minx, x); maxx = max(maxx, x)
                miny = min(miny, y); maxy = max(maxy, y)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < sw and 0 <= ny < sh and not visited[ny * sw + nx] and px[nx, ny] >= 96:
                        visited[ny * sw + nx] = 1
                        dq.append((nx, ny))
            frac = area / (sw * sh)
            if frac >= min_frac:
                comps.append(((minx, miny, maxx, maxy), frac))
    comps.sort(key=lambda c: -c[1])
    return comps


def hsv_stats(crop: Image.Image) -> tuple[float, float, float]:
    """裁剪区的平均 H/S/V（H 度数）。"""
    import colorsys
    rgb = crop.convert("RGB").resize((32, 32))
    hs, ss, vs = [], [], []
    for p in rgb.getdata():
        if True:
            h, s, v = colorsys.rgb_to_hsv(p[0] / 255, p[1] / 255, p[2] / 255)
            hs.append(h * 360); ss.append(s); vs.append(v)
    n = len(hs)
    return (sum(hs) / n, sum(ss) / n, sum(vs) / n)


def ascii_preview(rgba: Image.Image, width: int = 46) -> str:
    w, h = rgba.size
    nh = max(1, int(width * h / w * 0.5))
    im = rgba.resize((width, nh))
    px = im.load()
    lines = []
    for y in range(nh):
        row = []
        for x in range(width):
            r, g, b, a = px[x, y]
            if a < 90:
                row.append(" ")
            else:
                lum = (r * 299 + g * 587 + b * 114) // 1000
                row.append(RAMP[min(9, (255 - lum) * 10 // 256)])
        lines.append("".join(row))
    return "\n".join(lines)


def eye_candidates(rgba: Image.Image, bbox: tuple[int, int, int, int]) -> list[tuple[int, int, int]]:
    """在主体 bbox 内找白色圆形斑块（眼睛候选）。"""
    x0, y0, x1, y1 = bbox
    w, h = rgba.size
    crop = rgba.crop((max(0, x0), max(0, y0), min(w, x1), min(h, y1)))
    cw, ch = crop.size
    if cw < 10 or ch < 10:
        return []
    small = crop.resize((min(160, cw), int(min(160, cw) * ch / cw)), Image.BILINEAR)
    sw, sh = small.size
    px = small.convert("RGB").load()
    apx = small.getchannel("A").load()
    from collections import deque
    visited = bytearray(sw * sh)
    out = []
    for sy in range(sh):
        for sx in range(sw):
            if visited[sy * sw + sx] or apx[sx, sy] < 128:
                continue
            r, g, b = px[sx, sy]
            if not (r > 215 and g > 215 and b > 215):
                continue
            dq = deque([(sx, sy)]); visited[sy * sw + sx] = 1
            minx = maxx = sx; miny = maxy = sy; area = 0
            while dq:
                x, y = dq.popleft(); area += 1
                minx = min(minx, x); maxx = max(maxx, x)
                miny = min(miny, y); maxy = max(maxy, y)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < sw and 0 <= ny < sh and not visited[ny * sw + nx] and apx[nx, ny] >= 128:
                        r2, g2, b2 = px[nx, ny]
                        if r2 > 210 and g2 > 210 and b2 > 210:
                            visited[ny * sw + nx] = 1
                            dq.append((nx, ny))
            bw, bh = maxx - minx + 1, maxy - miny + 1
            if area >= (0.006 * sw * sh) and 0.55 <= bw / max(1, bh) <= 1.9 and area / (bw * bh) > 0.62:
                fx = (minx + maxx) / 2 / sw
                fy = (miny + maxy) / 2 / sh
                out.append((round(fx, 3), round(fy, 3), round(area / (sw * sh), 4)))
    out.sort(key=lambda t: -t[2])
    return out[:6]


def main() -> None:
    for name in SOURCES:
        path = DESKTOP / name
        if not path.exists():
            print(f"[{name}] MISSING")
            continue
        im = Image.open(path)
        print(f"\n===== {name}: {im.size} mode={im.mode}")
        rgba, ratio = flood_remove_bg(im)
        print(f"flood_removed={ratio:.1%} bg={border_bg_color(im.convert('RGB'))}")
        comps = components(rgba, min_frac=0.004)
        print(f"components(>=0.4%): {len(comps)}")
        for i, (bbox, frac) in enumerate(comps[:6]):
            x0, y0, x1, y1 = bbox
            bw, bh = x1 - x0, y1 - y0
            w, h = rgba.size
            crop = rgba.crop((max(0, x0 - 2), max(0, y0 - 2), min(w, x1 + 3), min(h, y1 + 3)))
            hue, sat, val = hsv_stats(crop)
            blueish = BLUE_H[0] <= hue <= BLUE_H[1] and sat > 0.25
            print(f"  comp{i}: bbox={bw}x{bh} frac={frac:.2%} hsv=({hue:.0f},{sat:.2f},{val:.2f}) blue={blueish}")
            if blueish and bw >= 40:
                crop.save(OUT / f"{Path(name).stem}_comp{i}.png")
                eyes = eye_candidates(crop, (0, 0, crop.width, crop.height))
                if eyes:
                    print(f"    eyes(rel): {eyes}")
                prev = ascii_preview(crop)
                (OUT / f"{Path(name).stem}_comp{i}.txt").write_text(prev, encoding="utf-8")
        rgba.save(OUT / f"{Path(name).stem}_cut.png")


if __name__ == "__main__":
    main()
