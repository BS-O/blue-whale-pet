#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""蓝鲸桌宠 · 美术资产验收脚本（SPEC §4 / §8）。

校验内容：
  1. assets/mascot/manifest.json 结构（14 state、帧数 2~5、durations、loop、canvas、anchor、key_color）
  2. 全部精灵帧：512×512 RGBA、单帧 ≤60KB、alpha 非空比例、包围盒/锚点/居中偏差、
     帧间包围盒抖动 ≤6px、轮缘像素为深色描边（Windows 色键透明防脏边）
  3. 图标：app.ico(256/128/64/48/32/16)、tray.ico(16/32/48)、app.png(512)、
     SVG、hicolor 16~512；16px 托盘图标可辨识度（占比/蓝/白/深色像素）
  4. 安装器插画：banner 600×160、side 164×314、setup.ico
  5. 预览图 contact_sheet.png、参考图目录、tools/gen_assets.py
  6. 总体积 ≤8MB

用法：py tools/check_assets.py
退出码：0 = 全部通过；1 = 有失败项。
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "assets"
MASTER = A / "mascot" / "master"
ICONS = A / "icons"
INSTALLER = A / "installer"
PREVIEW = A / "preview"

CANVAS = 512
ANCHOR = (256, 496)
FRAME_LIMIT = 60 * 1024          # 单帧 60KB
TOTAL_LIMIT = 8 * 1024 * 1024    # assets 总体积 8MB
REQUIRED = ["idle", "blink", "happy", "laugh", "talk", "think", "sleep",
            "surprise", "sad", "angry", "love", "drag", "wave", "eat"]
# 包围盒容差：呼吸挤压 + ±4px 浮动（Lead 要求 ±3~5px 生命感），脚底锚点允许 ±5px
TOP_MIN, TOP_MAX = 139, 160
BOT_MIN, BOT_MAX = 488, 501
CX_TOL = 16
SPREAD_TOL = 9                   # 同一 state 内帧间包围盒抖动上限（px）

FAIL = []


def fail(msg):
    FAIL.append(msg)
    print(f"  [FAIL] {msg}")


def ok(msg):
    print(f"  [ ok ] {msg}")


def ico_sizes(path):
    """解析 ICO 目录，返回 [(w,h), ...]（不依赖 Pillow 的缩放行为）。"""
    data = path.read_bytes()
    if len(data) < 6:
        return []
    reserved, typ, count = struct.unpack("<HHH", data[:6])
    if reserved != 0 or typ != 1:
        return []
    out = []
    for i in range(count):
        off = 6 + i * 16
        if off + 16 > len(data):
            return out
        w, h = data[off], data[off + 1]
        out.append((w or 256, h or 256))
    return out


def alpha_mask(img, thr=8):
    return img.getchannel("A").point(lambda v: 255 if v >= thr else 0)


def bbox_of(img):
    b = alpha_mask(img).getbbox()
    return b  # (l, t, r, b) 右/下为开区间


def edge_stats(img, bbox):
    """轮缘像素统计：返回 (边缘像素数, 平均最大通道, 浅色边缘比例)。"""
    m = alpha_mask(img)
    eroded = m.filter(ImageFilter.MinFilter(3))
    boundary = ImageChops.subtract(m, eroded)
    l, t, r, b = bbox
    cbox = (max(0, l - 1), max(0, t - 1), min(img.width, r + 1), min(img.height, b + 1))
    bd = boundary.crop(cbox).tobytes()
    rgb = img.convert("RGB").crop(cbox).tobytes()
    n = 0
    total = 0
    light = 0
    for i, v in enumerate(bd):
        if v > 0:
            n += 1
            r0, g0, b0 = rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2]
            mx = max(r0, g0, b0)
            total += mx
            if mx > 150:
                light += 1
    if n == 0:
        return 0, 999, 1.0
    return n, total / n, light / n


def check_manifest():
    print("\n[1] manifest.json")
    path = A / "mascot" / "manifest.json"
    if not path.exists():
        fail("manifest.json 不存在")
        return None
    try:
        man = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        fail(f"manifest.json 无法解析: {e}")
        return None
    if man.get("version") != 1:
        fail(f"version 应为 1，实际 {man.get('version')}")
    canvas = man.get("canvas", {})
    want = {"w": CANVAS, "h": CANVAS, "anchor_x": ANCHOR[0], "anchor_y": ANCHOR[1]}
    if canvas != want:
        fail(f"canvas 应为 {want}，实际 {canvas}")
    if man.get("key_color") != "#010203":
        fail(f"key_color 应为 #010203，实际 {man.get('key_color')}")
    states = man.get("states", {})
    if sorted(states) != sorted(REQUIRED):
        missing = set(REQUIRED) - set(states)
        extra = set(states) - set(REQUIRED)
        fail(f"state 集合不符：缺少 {sorted(missing)}，多出 {sorted(extra)}")
    else:
        ok(f"14 个 state 齐全：{', '.join(REQUIRED)}")
    total = 0
    for st in REQUIRED:
        info = states.get(st)
        if not isinstance(info, dict):
            fail(f"state {st} 缺失或结构错误")
            continue
        frames = info.get("frames")
        durs = info.get("durations")
        if not isinstance(frames, list) or not 2 <= len(frames) <= 5:
            fail(f"{st}: frames 数量应 2~5，实际 {frames}")
            continue
        if not isinstance(durs, list) or len(durs) != len(frames):
            fail(f"{st}: durations 长度应与 frames 一致")
        elif not all(isinstance(d, int) and d > 0 for d in durs):
            fail(f"{st}: durations 必须为正整数")
        if not isinstance(info.get("loop"), bool):
            fail(f"{st}: loop 必须为 bool")
        for name in frames:
            if not isinstance(name, str) or not (MASTER / f"{name}.png").exists():
                fail(f"{st}: 帧文件缺失 {name}.png")
        total += len(frames)
    ds = man.get("default_state")
    if ds not in REQUIRED:
        fail(f"default_state 非法：{ds}")
    ok(f"manifest 可解析，共 {total} 帧")
    return man


def check_frames(man):
    print("\n[2] 精灵帧（尺寸/模式/alpha/锚点/抖动/描边）")
    if not man:
        return
    max_size = 0
    all_frames = []
    state_bbox = {}
    for st in REQUIRED:
        for name in man["states"][st]["frames"]:
            p = MASTER / f"{name}.png"
            if not p.exists():
                continue
            sz = p.stat().st_size
            max_size = max(max_size, sz)
            if sz > FRAME_LIMIT:
                fail(f"{name}.png 体积 {sz/1024:.0f}KB > 60KB")
            try:
                img = Image.open(p)
            except Exception as e:  # noqa: BLE001
                fail(f"{name}.png 无法打开: {e}")
                continue
            if img.size != (CANVAS, CANVAS):
                fail(f"{name}.png 尺寸 {img.size} != 512×512")
            if img.mode != "RGBA":
                fail(f"{name}.png 模式 {img.mode} != RGBA")
            img = img.convert("RGBA")
            bbox = bbox_of(img)
            if not bbox:
                fail(f"{name}.png 全透明")
                continue
            l, t, r, b = bbox
            w, h = r - l, b - t
            alpha = img.getchannel("A")
            hist = alpha.histogram()
            coverage = 1.0 - hist[0] / (CANVAS * CANVAS)
            if not 0.10 <= coverage <= 0.80:
                fail(f"{name}.png alpha 覆盖率 {coverage:.2f} 异常")
            # 包围盒 / 锚点 / 居中
            if not TOP_MIN <= t <= TOP_MAX:
                fail(f"{name}.png 顶部 {t} 超出 [{TOP_MIN},{TOP_MAX}]")
            if not BOT_MIN <= b <= BOT_MAX:
                fail(f"{name}.png 脚底 {b} 超出 [{BOT_MIN},{BOT_MAX}]（锚点 496）")
            cx = (l + r) / 2
            if abs(cx - ANCHOR[0]) > CX_TOL:
                fail(f"{name}.png 水平中心 {cx:.0f} 偏离锚点 x=256 超过 {CX_TOL}px")
            if l < 1 or t < 1 or r > CANVAS - 1 or b > CANVAS - 1:
                fail(f"{name}.png 触边（可能被裁切）bbox={bbox}")
            # 轮缘必须是深色描边（Windows 色键透明）
            n_edge, mean_max, light_ratio = edge_stats(img, bbox)
            if n_edge < 100:
                fail(f"{name}.png 轮缘像素过少 {n_edge}")
            elif mean_max > 110 or light_ratio > 0.02:
                fail(f"{name}.png 轮缘偏浅（均值 {mean_max:.0f}，浅色占比 "
                     f"{light_ratio:.1%}），色键透明会出现脏边")
            state_bbox.setdefault(st, []).append((t, b, l, r))
            all_frames.append((name, bbox))
    # 同一 state 内帧间抖动
    worst = 0
    for st, boxes in state_bbox.items():
        ts = [x[0] for x in boxes]
        bs = [x[1] for x in boxes]
        ls = [x[2] for x in boxes]
        rs = [x[3] for x in boxes]
        spread = max(max(ts) - min(ts), max(bs) - min(bs),
                     max(ls) - min(ls), max(rs) - min(rs))
        worst = max(worst, spread)
        if spread > SPREAD_TOL:
            fail(f"{st}: 帧间包围盒抖动 {spread}px > {SPREAD_TOL}px")
    ok(f"{len(all_frames)} 帧检查完成；最大单帧 {max_size/1024:.1f}KB；"
       f"组内最大抖动 {worst}px")


def check_icons():
    print("\n[3] 图标")
    app = ICONS / "app.ico"
    if not app.exists():
        fail("app.ico 不存在")
    else:
        sizes = ico_sizes(app)
        need = {(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)}
        if not need <= set(sizes):
            fail(f"app.ico 尺寸集合 {sorted(sizes)} 缺少 {sorted(need - set(sizes))}")
        else:
            ok(f"app.ico 尺寸 {sorted(s[0] for s in sizes)}")
    tray = ICONS / "tray.ico"
    if not tray.exists():
        fail("tray.ico 不存在")
    else:
        sizes = ico_sizes(tray)
        need = {(16, 16), (32, 32), (48, 48)}
        if not need <= set(sizes):
            fail(f"tray.ico 尺寸集合 {sorted(sizes)} 缺少 {sorted(need - set(sizes))}")
        else:
            ok(f"tray.ico 尺寸 {sorted(s[0] for s in sizes)}")
        # 16×16 可辨识度：占比、蓝色、白色眼睛、深色描边
        im = Image.open(tray)
        im.size = (16, 16)
        im.load()
        im = im.convert("RGBA")
        px = list(im.getdata())
        opaque = [p for p in px if p[3] > 40]
        if not 0.25 <= len(opaque) / 256 <= 0.98:
            fail(f"16px 图标不透明占比 {len(opaque)/256:.2f} 异常")
        blue = sum(1 for p in opaque if p[2] > 120 and p[2] > p[0])
        white = sum(1 for p in opaque if min(p[:3]) > 200)
        dark = sum(1 for p in opaque if max(p[:3]) < 80)
        if blue < 20:
            fail(f"16px 图标蓝色像素过少 ({blue})")
        if white < 4:
            fail(f"16px 图标缺少亮色眼睛像素 ({white})")
        if dark < 8:
            fail(f"16px 图标缺少深色描边 ({dark})")
        if blue >= 20 and white >= 4 and dark >= 8:
            ok(f"16px 托盘图标可辨识（蓝 {blue} / 白 {white} / 深色 {dark} 像素）")
    app_png = ICONS / "app.png"
    if not app_png.exists():
        fail("app.png 不存在")
    else:
        im = Image.open(app_png)
        if im.size != (512, 512) or im.mode != "RGBA":
            fail(f"app.png 应为 512×512 RGBA，实际 {im.size} {im.mode}")
        else:
            ok("app.png 512×512 RGBA")
    svg = ICONS / "blue-whale-pet.svg"
    if not svg.exists():
        fail("blue-whale-pet.svg 不存在")
    else:
        txt = svg.read_text(encoding="utf-8", errors="ignore")
        for token in ("<svg", 'viewBox="0 0 512 512"', "#4D6BFE", "#0B1330"):
            if token not in txt:
                fail(f"SVG 缺少 {token}")
        if len(txt) < 1500:
            fail("SVG 内容过短")
        ok(f"SVG 矢量图标 {len(txt)} 字符")
    for n in (16, 24, 32, 48, 64, 128, 256, 512):
        p = ICONS / "hicolor" / f"{n}x{n}" / "apps" / "blue-whale-pet.png"
        if not p.exists():
            fail(f"hicolor {n}x{n} 缺失")
            continue
        im = Image.open(p)
        if im.size != (n, n):
            fail(f"hicolor {n}x{n} 尺寸 {im.size} 不符")
        if im.mode not in ("RGBA", "P") and "transparency" not in im.info:
            fail(f"hicolor {n}x{n} 无透明通道")
    ok("hicolor 16/24/32/48/64/128/256/512 齐全")


def check_installer():
    print("\n[4] 安装器插画")
    specs = {"banner.png": (600, 160), "side.png": (164, 314)}
    for name, size in specs.items():
        p = INSTALLER / name
        if not p.exists():
            fail(f"{name} 不存在")
            continue
        im = Image.open(p)
        if im.size != size:
            fail(f"{name} 尺寸 {im.size} != {size}")
        elif im.mode != "RGBA":
            fail(f"{name} 模式 {im.mode} != RGBA")
        else:
            ok(f"{name} {size[0]}×{size[1]} RGBA")
    setup = INSTALLER / "setup.ico"
    if not setup.exists():
        fail("setup.ico 不存在")
    else:
        sizes = ico_sizes(setup)
        if not {(16, 16), (32, 32), (48, 48)} <= set(sizes):
            fail(f"setup.ico 尺寸 {sorted(sizes)} 不满足 16/32/48")
        else:
            ok(f"setup.ico 尺寸 {sorted(s[0] for s in sizes)}")


def check_misc():
    print("\n[5] 预览 / 参考 / 脚本 / 体积")
    cs = PREVIEW / "contact_sheet.png"
    if not cs.exists():
        fail("contact_sheet.png 不存在")
    else:
        im = Image.open(cs)
        if im.width < 600 or im.height < 1200:
            fail(f"contact_sheet.png 过小 {im.size}")
        else:
            ok(f"contact_sheet.png {im.width}×{im.height}")
    refs = A / "source" / "references"
    if not refs.exists():
        fail("assets/source/references 不存在")
    else:
        n = len(list(refs.iterdir()))
        ok(f"参考素材 {n} 个文件")
    for name in ("NOTICE.md",):
        if not (A / "source" / name).exists():
            fail(f"assets/source/{name} 不存在")
    if not (ROOT / "tools" / "gen_assets.py").exists():
        fail("tools/gen_assets.py 不存在")
    total = sum(p.stat().st_size for p in A.rglob("*") if p.is_file())
    if total > TOTAL_LIMIT:
        fail(f"assets 总体积 {total/1024/1024:.2f}MB > 8MB")
    else:
        ok(f"assets 总体积 {total/1024/1024:.2f}MB")
    # 帧文件总数
    n_png = len(list(MASTER.glob("*.png")))
    if n_png != 38:
        fail(f"master 帧数 {n_png} != 38")
    else:
        ok("master 帧数 38")


def main():
    print("=" * 64)
    print("蓝鲸桌宠 · 美术资产验收（SPEC §4）")
    print("=" * 64)
    man = check_manifest()
    check_frames(man)
    check_icons()
    check_installer()
    check_misc()
    print("\n" + "=" * 64)
    if FAIL:
        print(f"结果：失败 {len(FAIL)} 项")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print("结果：全部通过 [PASS]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
