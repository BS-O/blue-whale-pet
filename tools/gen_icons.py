"""从用户提供的候选图（桌面 1/2/3/5.png）生成全套应用图标。

流程：
  1) 背景估计（四角中值色）+ 边界洪泛抠图（容差自适应），失败回退圆角裁切
  2) 主体裁边、羽化、方形画布居中
  3) 依据主体主色自适应底色：偏蓝主体 → 浅底+品牌蓝描边环；否则 → 品牌蓝底
  4) 产出 4 个候选图标 + ASCII 轮廓预览（供无图像输入的模型选型）+ 评分
  5) --pick N 指定候选后重新生成全套：app.ico/app.png/tray.ico/setup.ico/hicolor/svg

用法：
  py tools/gen_icons.py            # 生成候选并自动选优
  py tools/gen_icons.py --pick 5   # 强制用 5 号候选重新生成全套
"""
from __future__ import annotations

import argparse
import base64
import colorsys
import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "assets" / "icons"
HICOLOR = ICONS / "hicolor"
CANDIDATES_DIR = ROOT / "qa" / "out" / "icon_candidates"
SOURCES = [1, 2, 3, 5]  # 桌面候选（用户说明含 4.png，实际不存在）
BRAND_BLUE = (77, 107, 254)        # #4D6BFE
BRAND_BLUE_DARK = (43, 63, 158)
LIGHT_BG = (247, 249, 255)
HICO_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
ICO_SIZES = (256, 128, 64, 48, 32, 16)


def load_sources() -> dict[int, Image.Image]:
    out = {}
    desktop = Path.home() / "Desktop"
    for i in SOURCES:
        p = desktop / f"{i}.png"
        if p.exists():
            out[i] = Image.open(p).convert("RGB")
    return out


def border_bg_color(im: Image.Image) -> tuple[tuple[int, int, int], float]:
    """返回 (背景色中值, 边界均匀度0~1)。"""
    w, h = im.size
    px = im.load()
    samples = []
    for x in range(0, w, max(1, w // 100)):
        samples.append(px[x, 0]); samples.append(px[x, h - 1])
    for y in range(0, h, max(1, h // 100)):
        samples.append(px[0, y]); samples.append(px[w - 1, y])
    rs = sorted(s[0] for s in samples); gs = sorted(s[1] for s in samples); bs = sorted(s[2] for s in samples)
    mid = len(samples) // 2
    bg = (rs[mid], gs[mid], bs[mid])
    var = sum(abs(s[0] - bg[0]) + abs(s[1] - bg[1]) + abs(s[2] - bg[2]) for s in samples) / (len(samples) * 3)
    uniform = max(0.0, 1.0 - var / 60.0)
    return bg, uniform


def flood_remove_bg(im: Image.Image, tol: int = 30) -> Image.Image:
    """从边界洪泛移除与背景相近的连通区域，返回 RGBA。"""
    w, h = im.size
    px = im.load()
    bg, uniform = border_bg_color(im)
    tol_i = int(max(18, tol * (1.6 - uniform)))  # 背景越花哨容差越小
    visited = bytearray(w * h)
    q = deque()
    for x in range(w):
        q.append((x, 0)); q.append((x, h - 1))
    for y in range(h):
        q.append((0, y)); q.append((w - 1, y))
    def near(c1, c2):
        return abs(c1[0] - c2[0]) + abs(c1[1] - c2[1]) + abs(c1[2] - c2[2]) <= tol_i * 3
    while q:
        x, y = q.popleft()
        if x < 0 or y < 0 or x >= w or y >= h:
            continue
        idx = y * w + x
        if visited[idx]:
            continue
        visited[idx] = 1
        if not near(px[x, y], bg):
            continue
        q.extend(((x+1, y), (x-1, y), (x, y+1), (x, y-1)))
    alpha = Image.new("L", (w, h), 255)
    ap = alpha.load()
    removed = 0
    for idx in range(w * h):
        if visited[idx]:
            x, y = idx % w, idx // w
            if near(px[x, y], bg):
                ap[x, y] = 0
                removed += 1
    rgba = im.convert("RGBA")
    rgba.putalpha(alpha)
    return rgba, removed / (w * h)


def rounded_crop(im: Image.Image) -> Image.Image:
    """背景复杂时的回退：中心最大方形裁切，圆角遮罩。"""
    w, h = im.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    im = im.crop((left, top, left + side, top + side)).convert("RGBA")
    mask = Image.new("L", (side * 4, side * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, side * 4 - 1, side * 4 - 1), radius=side, fill=255)
    mask = mask.resize((side, side), Image.LANCZOS)
    im.putalpha(mask)
    return im


def largest_component(rgba: Image.Image, min_frac: float = 0.04) -> tuple[Image.Image, int]:
    """在 alpha 上做连通域分析；多主体（贴纸表格）时切出最大主体。

    返回 (仅含最大主体的 RGBA, 检出的主体数)。单主体时原样返回。
    """
    w, h = rgba.size
    scale = min(1.0, 720.0 / max(w, h))
    sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
    small = rgba.resize((sw, sh), Image.BILINEAR)
    ap = small.getchannel("A").load()
    labels = [0] * (sw * sh)
    sizes: dict[int, int] = {}
    cur = 0
    for y in range(sh):
        for x in range(sw):
            idx = y * sw + x
            if labels[idx] or ap[x, y] < 48:
                continue
            cur += 1
            q = deque([(x, y)])
            labels[idx] = cur
            n = 0
            while q:
                cx, cy = q.popleft()
                n += 1
                for nx, ny in ((cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1)):
                    if 0 <= nx < sw and 0 <= ny < sh:
                        nidx = ny * sw + nx
                        if not labels[nidx] and ap[nx, ny] >= 48:
                            labels[nidx] = cur
                            q.append((nx, ny))
            sizes[cur] = n
    if not sizes:
        return rgba, 0
    total = sw * sh
    big = [c for c, n in sizes.items() if n >= total * min_frac]
    if len(big) <= 1:
        return rgba, len(sizes)
    best = max(big, key=lambda c: sizes[c])
    xs = [i % sw for i, v in enumerate(labels) if v == best]
    ys = [i // sw for i, v in enumerate(labels) if v == best]
    x0, x1 = int(min(xs) / scale), int((max(xs) + 1) / scale)
    y0, y1 = int(min(ys) / scale), int((max(ys) + 1) / scale)
    pad = int(max(x1 - x0, y1 - y0) * 0.04)
    box = (max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad))
    out = rgba.crop(box)
    # 仅保留最大主体的像素
    mask = Image.new("L", out.size, 0)
    mp = mask.load()
    op = out.getchannel("A").load()
    for yy in range(out.size[1]):
        for xx in range(out.size[0]):
            mp[xx, yy] = 255 if op[xx, yy] >= 48 else 0
    mask = mask.filter(ImageFilter.GaussianBlur(0.6))
    out.putalpha(mask)
    return out, len(sizes)


def extract_subject(im: Image.Image) -> tuple[Image.Image, dict]:
    """抠图 + 裁边 + 方形衬垫；返回 (RGBA 方图, 统计)。"""
    bg, uniform = border_bg_color(im)
    stats = {"uniform": round(uniform, 2)}
    if uniform > 0.55:
        rgba, removed = flood_remove_bg(im)
        stats["removed_pct"] = round(removed * 100, 1)
        a = rgba.getchannel("A")
        bbox = a.getbbox()
        # 洪泛失败（几乎没删或删太多）→ 回退
        if not bbox or removed < 0.05 or removed > 0.92:
            rgba = rounded_crop(im)
            stats["mode"] = "rounded_fallback"
        else:
            stats["mode"] = "flood"
    else:
        rgba = rounded_crop(im)
        stats["mode"] = "rounded"
    bbox = rgba.getchannel("A").getbbox() or (0, 0, *rgba.size)
    rgba = rgba.crop(bbox)
    if stats.get("mode") == "flood":
        rgba, ncomp = largest_component(rgba)
        stats["components"] = ncomp
    side = max(rgba.size)
    pad = int(side * 0.06)
    square = Image.new("RGBA", (side + pad * 2, side + pad * 2), (0, 0, 0, 0))
    square.paste(rgba, ((square.size[0] - rgba.size[0]) // 2, (square.size[1] - rgba.size[1]) // 2), rgba)
    alpha = square.getchannel("A").filter(ImageFilter.GaussianBlur(0.8))
    square.putalpha(alpha)
    stats["subject_px"] = square.size
    return square, stats


def subject_is_blue(im: Image.Image) -> bool:
    px = list(im.resize((40, 40)).getdata())
    blue = 0; total = 0
    for r, g, b, a in px:
        if a < 40:
            continue
        total += 1
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if 0.5 <= h <= 0.72 and s > 0.25:
            blue += 1
    return total > 0 and blue / total > 0.35


def dominant_color_name(im: Image.Image) -> str:
    px = [p for p in im.resize((40, 40)).getdata() if p[3] > 60]
    if not px:
        return "empty"
    rs = sum(p[0] for p in px) // len(px); gs = sum(p[1] for p in px) // len(px); bs = sum(p[2] for p in px) // len(px)
    h, s, v = colorsys.rgb_to_hsv(rs / 255, gs / 255, bs / 255)
    hue = int(h * 360)
    name = ("红" if hue < 20 or hue >= 330 else "橙" if hue < 45 else "黄" if hue < 70 else "绿" if hue < 160
            else "青" if hue < 200 else "蓝" if hue < 260 else "紫" if hue < 300 else "品红")
    return f"{name}(RGB~{rs},{gs},{bs})"


def compose_icon(subject: Image.Image, size: int = 1024) -> Image.Image:
    """品牌风图标：自适应底 + 描边环 + 居中主体。"""
    blue_body = subject_is_blue(subject)
    bg_top = LIGHT_BG if blue_body else (BRAND_BLUE[0] + 18, BRAND_BLUE[1] + 18, BRAND_BLUE[2] + 10)
    bg_bot = (226, 232, 252) if blue_body else BRAND_BLUE_DARK
    ring = BRAND_BLUE if blue_body else (255, 255, 255)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size))
    gp = grad.load()
    for y in range(size):
        t = y / (size - 1)
        c = tuple(int(bg_top[i] + (bg_bot[i] - bg_top[i]) * t) for i in range(3)) + (255,)
        for x in range(size):
            gp[x, y] = c
    mask = Image.new("L", (size * 2, size * 2), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size * 2 - 1, size * 2 - 1), radius=int(size * 2 * 0.22), fill=255)
    canvas.paste(grad, (0, 0), mask.resize((size, size), Image.LANCZOS))
    draw = ImageDraw.Draw(canvas)
    m = int(size * 0.035)
    draw.rounded_rectangle((m, m, size - m - 1, size - m - 1), radius=int(size * 0.20), outline=ring + (255,), width=max(3, size // 110))
    fit = int(size * 0.80)
    subj = subject.resize((fit, fit), Image.LANCZOS)
    canvas.alpha_composite(subj, ((size - fit) // 2, (size - fit) // 2))
    return canvas


def ascii_preview(im: Image.Image, cols: int = 56) -> str:
    """透明度 ASCII 轮廓（深块=实体）。"""
    rows = max(10, cols // 2)
    small = im.resize((cols, rows))
    ramp = " .:-=+*#%@"
    out = []
    a = small.getchannel("A")
    ap = a.load()
    for y in range(rows):
        line = ""
        for x in range(cols):
            v = ap[x, y]
            line += ramp[min(9, v * 10 // 256)]
        out.append(line)
    return "\n".join(out)


def score_subject(subject: Image.Image, stats: dict) -> float:
    s = 0.0
    s += 2.0 if stats.get("mode") == "flood" else 0.0
    w, h = subject.size
    s += 1.0 if min(w, h) >= 500 else 0.0
    s += 1.0 - abs(1.0 - w / h)  # 越接近方形越高
    if stats.get("removed_pct") is not None:
        r = stats["removed_pct"]
        s += 1.0 if 8 <= r <= 70 else 0.0
    return round(s, 2)


def gen_all(pick: int | None = None) -> None:
    sources = load_sources()
    if not sources:
        print("NO SOURCES on Desktop"); return
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    for i, im in sorted(sources.items()):
        work = im.copy()
        work.thumbnail((1400, 1400), Image.LANCZOS)
        subject, stats = extract_subject(work)
        icon = compose_icon(subject)
        score = score_subject(subject, stats)
        results[i] = {"subject": subject, "icon": icon, "stats": stats, "score": score}
        icon.resize((256, 256), Image.LANCZOS).save(CANDIDATES_DIR / f"candidate_{i}.png")
        print(f"--- 候选 {i}: score={score} stats={stats} 主色={dominant_color_name(subject)} ---")
        print(ascii_preview(subject, 56))
    pick_id = pick or max(results, key=lambda k: results[k]["score"])
    print(f"\nPICK = {pick_id} (auto)" if pick is None else f"\nPICK = {pick_id} (manual)")
    master = results[pick_id]["icon"].resize((1024, 1024), Image.LANCZOS)
    master.save(CANDIDATES_DIR / f"master_{pick_id}.png")

    ICONS.mkdir(parents=True, exist_ok=True)
    master.resize((512, 512), Image.LANCZOS).save(ICONS / "app.png")
    ico_im = master.resize((256, 256), Image.LANCZOS)
    ico_im.save(ICONS / "app.ico", sizes=[(s, s) for s in ICO_SIZES])
    ico_im.save(ICONS / "setup.ico", sizes=[(s, s) for s in ICO_SIZES])
    ico_im.save(ICONS / "tray.ico", sizes=[(48, 48), (32, 32), (16, 16)])
    for s in HICO_SIZES:
        p = HICOLOR / f"{s}x{s}" / "apps"
        p.mkdir(parents=True, exist_ok=True)
        master.resize((s, s), Image.LANCZOS).save(p / "blue-whale-pet.png")
    b64 = base64.b64encode(open(CANDIDATES_DIR / f"master_{pick_id}.png", "rb").read()).decode()
    (ICONS / "blue-whale-pet.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">'
        f'<image width="1024" height="1024" href="data:image/png;base64,{b64}"/></svg>',
        encoding="utf-8")
    # 安装器插画小图（banner 内嵌角标可后换，先同步 setup 源）
    print("WROTE: app.png/app.ico/tray.ico/setup.ico/hicolor*/blue-whale-pet.svg")
    # 对比拼图
    sheet = Image.new("RGBA", (256 * len(results) + 20 * (len(results) + 1), 300), (250, 250, 252, 255))
    x = 20
    for i in sorted(results):
        sheet.paste(results[i]["icon"].resize((256, 256), Image.LANCZOS), (x, 24), results[i]["icon"].resize((256, 256), Image.LANCZOS))
        x += 276
    sheet.save(ROOT / "docs" / "screenshots" / "icon_candidates.png")
    print("SHEET: docs/screenshots/icon_candidates.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pick", type=int, default=None)
    args = ap.parse_args()
    gen_all(args.pick)
