#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""蓝鲸桌宠（蓝色大肥鱼）· 正式美术资产生成器。

以 ``assets/source/references/`` 中 DeepSeek 官方蓝鲸 logo 为灵感与取色基础，
**程序化重绘** 为更圆更肥、深藏青粗描边、大眼 + 腮红的 Q 版桌宠精灵；
不使用官方素材原图（官方图仅用于取色/比例分析，见 ``--analyze``）。

产出（全部 RGBA PNG）：
  assets/mascot/master/<state>_<frame>.png   512×512，锚点 (256,496)，14 state / 38 帧
  assets/mascot/manifest.json                帧清单（SPEC §4.1）
  assets/icons/app.ico / app.png / tray.ico / blue-whale-pet.svg
  assets/icons/hicolor/<N>x<N>/apps/blue-whale-pet.png
  assets/installer/banner.png / side.png / setup.ico
  assets/preview/contact_sheet.png           表情总览（中文标签）

用法：
  py tools/gen_assets.py               # 生成全部资产
  py tools/gen_assets.py --analyze     # 顺带打印参考图取色/比例分析
  py tools/gen_assets.py --frame idle:0 --out <path.png>   # 调试单帧
  py tools/gen_assets.py --sheet <path.png>                # 调试 14 表情拼图

依赖：Pillow ≥ 9（无 numpy）。Python ≥ 3.9。
"""
from __future__ import annotations

import argparse
import io
import json
import math
import struct
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "assets"
MASTER = A / "mascot" / "master"
ICONS = A / "icons"
INSTALLER = A / "installer"
PREVIEW = A / "preview"

# ---------------------------------------------------------------- 基础常量
S = 512              # 成品画布边长
SS = 4               # 超采样倍数（4x 绘制 → LANCZOS 缩到 512）
CW = S * SS
ANCHOR = (256, 496)  # 脚底中心锚点

BRAND = (77, 107, 254)     # #4D6BFE 品牌蓝
BRAND_HI = (112, 140, 255)
BRAND_LO = (46, 68, 208)
DARK = (11, 19, 48)        # #0B1330 深藏青描边
KEY = "#010203"
WHITE = (255, 255, 255)
BELLY = (198, 216, 255)
BELLY_HI = (228, 238, 255)
BELLY_LO = (158, 182, 242)
BLUSH = (255, 122, 160)
MOUTH = (112, 30, 66)
TONGUE = (255, 118, 148)
TEAR = (152, 210, 255)
YELLOW = (255, 224, 130)

# 角色几何（512 画布坐标，锚点 BOT 为脚底）
CX = 232             # 身体中心 x
BOT = 489            # 轮廓内脚底 y（描边后 +7 = 496）
OUTLINE_PX = 7.0     # 成品描边宽度（px @512）
K_GROW = int(round(OUTLINE_PX * SS))          # 超采样下的描边半径
MAXF = K_GROW * 2 + 1                          # MaxFilter 尺寸（奇数）

# 表情表：state -> (帧数, 每帧时长, loop)
STATES = {
    "idle":     (4, [420, 420, 420, 420], True),
    "blink":    (3, [60, 90, 60], False),
    "happy":    (3, [220, 200, 240], False),
    "laugh":    (3, [140, 140, 160], False),
    "talk":     (3, [160, 160, 160], True),
    "think":    (3, [300, 300, 300], False),
    "sleep":    (3, [820, 980, 820], True),
    "surprise": (2, [170, 240], False),
    "sad":      (2, [520, 520], False),
    "angry":    (2, [220, 240], False),
    "love":     (2, [420, 420], True),
    "drag":     (2, [150, 150], True),
    "wave":     (3, [240, 240, 240], True),
    "eat":      (3, [260, 260, 260], True),
}
STATE_ZH = {
    "idle": "待机", "blink": "眨眼", "happy": "开心", "laugh": "大笑",
    "talk": "说话", "think": "思考", "sleep": "睡觉", "surprise": "惊讶",
    "sad": "难过", "angry": "生气", "love": "爱心", "drag": "拖拽",
    "wave": "挥手", "eat": "吃东西",
}
# 呼吸/挤压变体：键 -> (x 缩放, y 缩放)，绕 (CX, BOT) 缩放，脚底不动
SQUASH = {
    "N":  (1.000, 1.000),
    "Q1": (1.005, 0.995),
    "Q2": (1.010, 0.990),
    "S1": (0.996, 1.004),
    "S2": (0.991, 1.008),
}

CJK_FONTS = [
    "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc",
]


# ---------------------------------------------------------------- 小工具
def mix(c1, c2, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


def load_font(size, bold=False):
    paths = CJK_FONTS if not bold else CJK_FONTS
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def catmull(points, closed=True, samples=16):
    """Catmull-Rom 样条采样，返回平滑折线点集。"""
    pts = list(points)
    n = len(pts)
    out = []
    rng = n if closed else n - 1
    for i in range(rng):
        p0 = pts[(i - 1) % n] if closed else pts[max(i - 1, 0)]
        p1 = pts[i % n]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if closed else pts[min(i + 2, n - 1)]
        for j in range(samples):
            t = j / samples
            t2, t3 = t * t, t * t * t
            out.append((
                0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3),
            ))
    return out


def heart_points(cx, cy, r, samples=28):
    pts = []
    for i in range(samples):
        t = i / samples * math.tau
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x * r / 16.0, cy + y * r / 16.0))
    return pts


def star4_points(cx, cy, r, inner=0.34):
    pts = []
    for i in range(8):
        ang = -math.pi / 2 + i * math.pi / 4
        rr = r if i % 2 == 0 else r * inner
        pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr))
    return pts


def drop_points(cx, cy, r):
    return [(cx, cy - r * 1.55), (cx + r * 0.82, cy - r * 0.05),
            (cx + r * 0.45, cy + r * 0.82), (cx, cy + r),
            (cx - r * 0.45, cy + r * 0.82), (cx - r * 0.82, cy - r * 0.05)]


class Xf:
    """角色坐标 (512) → 画布像素坐标 的（含挤压）仿射变换。"""

    def __init__(self, scale, ox=0.0, oy=0.0, bx0=0.0, by0=0.0, sx=1.0, sy=1.0):
        self.scale, self.ox, self.oy = scale, ox, oy
        self.bx0, self.by0 = bx0, by0
        self.sx, self.sy = sx, sy
        self.avg = (sx + sy) / 2.0

    def p(self, x, y):
        return (self.ox + (x - self.bx0) * self.scale * self.sx,
                self.oy + (y - self.by0) * self.scale * self.sy)

    def poly(self, pts):
        return [self.p(x, y) for x, y in pts]

    def box(self, x, y, rx, ry):
        x0, y0 = self.p(x - rx, y - ry)
        x1, y1 = self.p(x + rx, y + ry)
        return [x0, y0, x1, y1]

    def w(self, v):
        """角色坐标线宽 → 画布像素线宽（不小于 1）。"""
        return max(1, int(round(v * self.scale * self.avg)))

    def font(self, size_char):
        return load_font(max(6, int(round(size_char * self.scale * self.avg))))


def mascot_xf(squash_key):
    sx, sy = SQUASH[squash_key]
    return Xf(SS, ox=CX * SS * (1 - sx), oy=BOT * SS * (1 - sy), sx=sx, sy=sy)


# ---------------------------------------------------------------- 角色轮廓
# 参考官方蓝鲸 logo（大圆头 + 上翘双叶尾鳍）重绘为正面 Q 版。
BODY_PATH = [
    (CX, 158), (CX + 58, 161), (CX + 104, 176), (CX + 138, 208),
    (CX + 156, 260), (CX + 159, 318), (CX + 152, 380), (CX + 128, 434),
    (CX + 80, 475), (CX, 489),
    (CX - 80, 474), (CX - 128, 434), (CX - 152, 380), (CX - 159, 318),
    (CX - 156, 260), (CX - 138, 208), (CX - 104, 176), (CX - 58, 161),
]
BODY = catmull(BODY_PATH, samples=12)


def cubic(p0, c1, c2, p1, n=10):
    """三次贝塞尔采样（不含起点）。"""
    out = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        out.append((
            mt ** 3 * p0[0] + 3 * mt ** 2 * t * c1[0] + 3 * mt * t ** 2 * c2[0] + t ** 3 * p1[0],
            mt ** 3 * p0[1] + 3 * mt ** 2 * t * c1[1] + 3 * mt * t ** 2 * c2[1] + t ** 3 * p1[1],
        ))
    return out


def _tail_outline():
    """上翘双叶尾鳍（官方 logo 记忆点）：上叶 + 右叶双尖角，中间 V 形缺口。"""
    a = (332, 332)      # 与身体连接（上）
    up = (386, 194)     # 上叶尖
    notch = (412, 262)  # 尾鳍缺口
    right = (452, 230)  # 右叶尖
    low = (404, 318)    # 下缘
    b = (350, 376)      # 与身体连接（下）
    pts = [a]
    pts += cubic(a, (342, 308), (362, 246), up)
    pts += cubic(up, (392, 212), (402, 238), notch)
    pts += cubic(notch, (422, 250), (432, 238), right)
    pts += cubic(right, (454, 264), (430, 296), low)
    pts += cubic(low, (386, 342), (368, 360), b)
    return pts


TAIL_POLY = _tail_outline()
# 左右胸鳍（旋转椭圆，身体轮廓的一部分）
FIN_PARTS = [
    (96, 424, 32, 27, 8),
    (356, 438, 32, 27, -8),
]


def stamp_ellipse(mask, xf, cx, cy, rx, ry, angle):
    """把旋转椭圆并入 L 掩膜。"""
    px, py = xf.p(cx, cy)
    prx = rx * xf.scale * xf.avg
    pry = ry * xf.scale * xf.avg
    pad = int(math.ceil(max(prx, pry))) + 6
    layer = Image.new("L", (pad * 2, pad * 2), 0)
    dd = ImageDraw.Draw(layer)
    c = pad
    dd.ellipse([c - prx, c - pry, c + prx, c + pry], fill=255)
    layer = layer.rotate(angle, resample=Image.BICUBIC, center=(c, c))
    mask.paste(255, (int(px) - pad, int(py) - pad), layer)


def body_only_mask(xf):
    m = Image.new("L", (CW, CW), 0)
    d = ImageDraw.Draw(m)
    d.polygon(xf.poly(BODY), fill=255)
    for (x, y, rx, ry, ang) in FIN_PARTS:
        stamp_ellipse(m, xf, x, y, rx, ry, ang)
    return m


def body_mask(xf):
    m = Image.new("L", (CW, CW), 0)
    d = ImageDraw.Draw(m)
    d.polygon(xf.poly(BODY), fill=255)
    d.polygon(xf.poly(TAIL_POLY), fill=255)
    for (x, y, rx, ry, ang) in FIN_PARTS:
        stamp_ellipse(m, xf, x, y, rx, ry, ang)
    return m


BELLY_PATH = [
    (CX, 470), (CX + 66, 460), (CX + 98, 420), (CX + 92, 378),
    (CX + 52, 356), (CX, 354), (CX - 46, 366), (CX - 92, 358),
    (CX - 116, 344), (CX - 120, 380), (CX - 100, 424), (CX - 52, 458),
]
BELLY_PTS = catmull(BELLY_PATH, samples=12)


def default_fill():
    """身体竖渐变（品牌蓝上下过渡）。"""
    g = Image.new("RGBA", (1, S))
    for y in range(S):
        t = y / (S - 1)
        if t < 0.42:
            c = mix(BRAND_HI, BRAND, t / 0.42)
        else:
            c = mix(BRAND, BRAND_LO, (t - 0.42) / 0.58)
        g.putpixel((0, y), c + (255,))
    return g.resize((CW, CW), Image.BILINEAR)


def shifted(img, dx, dy):
    return ImageChops.offset(img, int(dx), int(dy))


def dilate(mask, radius):
    """快速形态学膨胀：多方向平移取并集（比大核 MaxFilter 快百倍）。"""
    r = int(round(radius))
    if r <= 0:
        return mask
    dirs = max(12, min(48, int(r * 1.8)))
    out = mask
    for i in range(dirs):
        a = i * math.tau / dirs
        out = ImageChops.lighter(
            out, shifted(mask, math.cos(a) * r, math.sin(a) * r))
    return out


def dilate_fast(mask, radius):
    """大画布时在半分辨率下膨胀再放大，速度提升约 4 倍。"""
    r = float(radius)
    if mask.width <= 640 or r <= 8:
        return dilate(mask, r)
    half = mask.resize((mask.width // 2, mask.height // 2), Image.BILINEAR)
    out = dilate(half, r / 2.0)
    return out.resize(mask.size, Image.BILINEAR)


def inner_rim(mask, dx, dy):
    """内侧边缘带：mask - 平移后的 mask（半分辨率计算后放大）。"""
    half = mask.resize((mask.width // 2, mask.height // 2), Image.BILINEAR)
    rim = ImageChops.subtract(half, shifted(half, dx / 2.0, dy / 2.0))
    return rim.resize(mask.size, Image.BILINEAR)


def apply_clip(dst, layer, mask):
    dst.paste(layer, (0, 0), mask)


def build_body_cache(squash_key):
    """返回该挤压变体下 512 成品身体层（含描边/渐层/肚皮/高光）。"""
    xf = mascot_xf(squash_key)
    mask = body_mask(xf)
    bodyonly = body_only_mask(xf)

    # 1) 深藏青描边：掩膜外扩 K_GROW 像素
    grown = dilate_fast(mask, K_GROW)

    base = Image.new("RGBA", (CW, CW), DARK + (0,))
    base.paste(Image.new("RGBA", (CW, CW), DARK + (255,)), (0, 0), grown)

    # 2) 品牌蓝渐变填充
    fill = default_fill()
    base.paste(fill, (0, 0), mask)

    # 3) 左上内侧亮边（立体感，只作用于身体；细长尾巴不整体覆盖）
    rim = ImageChops.multiply(inner_rim(bodyonly, K_GROW * 0.9, K_GROW * 0.9), bodyonly)
    lay = Image.new("RGBA", (CW, CW), BRAND_HI + (215,))
    apply_clip(base, lay, rim)
    # 4) 右下内侧暗边
    rim2 = ImageChops.multiply(inner_rim(bodyonly, -K_GROW * 0.85, -K_GROW * 0.7), bodyonly)
    lay2 = Image.new("RGBA", (CW, CW), BRAND_LO + (200,))
    apply_clip(base, lay2, rim2)

    # 5) 肚皮（呼应官方 logo 的浅色负空间，带左侧上卷的小浪花尖）
    bm = Image.new("L", (CW, CW), 0)
    ImageDraw.Draw(bm).polygon(xf.poly(BELLY_PTS), fill=255)
    bm = ImageChops.multiply(bm, mask)
    base.paste(Image.new("RGBA", (CW, CW), BELLY + (255,)), (0, 0), bm)
    # 肚皮内侧高光（右下亮边）
    bhi = ImageChops.multiply(inner_rim(bm, -14, -10), bm)
    base.paste(Image.new("RGBA", (CW, CW), BELLY_HI + (230,)), (0, 0), bhi)
    # 肚皮上缘阴影
    blo = ImageChops.multiply(inner_rim(bm, 10, 12), bm)
    base.paste(Image.new("RGBA", (CW, CW), BELLY_LO + (170,)), (0, 0), blo)

    # 6) 头顶高光：左上月牙高光 + 两点小高光（只作用身体，都在轮廓内）
    crescent = ImageChops.multiply(inner_rim(bodyonly, K_GROW * 1.15, K_GROW * 1.9), bodyonly)
    base.paste(Image.new("RGBA", (CW, CW), (255, 255, 255, 30)), (0, 0), crescent)
    dots = Image.new("RGBA", (CW, CW), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dots)
    dd.ellipse(xf.box(CX - 76, 244, 11, 7), fill=(255, 255, 255, 120))
    dd.ellipse(xf.box(CX - 54, 222, 5.5, 4), fill=(255, 255, 255, 95))
    dmax = Image.new("L", (CW, CW), 0)
    dm2 = ImageDraw.Draw(dmax)
    dm2.ellipse(xf.box(CX - 76, 244, 11, 7), fill=255)
    dm2.ellipse(xf.box(CX - 54, 222, 5.5, 4), fill=255)
    base.alpha_composite(Image.composite(dots, Image.new("RGBA", (CW, CW), (0, 0, 0, 0)),
                                         ImageChops.multiply(dmax, bodyonly)))

    out = base.resize((S, S), Image.LANCZOS)
    return out


_BODY_CACHE = {}


def body_layer(squash_key):
    if squash_key not in _BODY_CACHE:
        _BODY_CACHE[squash_key] = build_body_cache(squash_key)
    return _BODY_CACHE[squash_key]


# ---------------------------------------------------------------- 面部绘制
EYE_L = (186, 322)
EYE_R = (278, 322)
EYE_RX, EYE_RY = 31, 37
MOUTH_P = (CX, 396)


def round_line(d, xf, p0, p1, width, fill):
    a = xf.p(*p0)
    b = xf.p(*p1)
    w = xf.w(width)
    d.line([a, b], fill=fill, width=w)
    r = w / 2
    for (x, y) in (a, b):
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def draw_eye(d, xf, ex, ey, kind, r=1.0, look=(0.0, 0.0), out=1.0):
    """单只眼睛。out: 外扩系数（惊讶时更大）。"""
    rx = EYE_RX * r * out
    ry = EYE_RY * r * out
    x0, y0 = xf.p(ex, ey)
    ow = xf.w(5.2)
    sclera = xf.box(ex, ey, rx, ry)
    if kind in ("open", "half", "sad", "surprise", "look_up", "wink", "angry"):
        d.ellipse(sclera, fill=WHITE, outline=DARK, width=ow)
        # 虹膜/瞳孔
        pw = 0.62 if kind == "surprise" else 0.60
        prx, pry = rx * pw, ry * pw
        if kind == "surprise":
            prx, pry = rx * 0.38, ry * 0.38
        px, py = ex + look[0] * rx * 0.30, ey + look[1] * ry * 0.30
        if kind == "half":
            py = ey + ry * 0.30
        if kind == "sad":
            py = ey + ry * 0.36
        if kind == "angry":
            py = ey + ry * 0.12
        d.ellipse(xf.box(px, py, prx, pry), fill=DARK)
        # 高光
        hr = rx * 0.24
        d.ellipse(xf.box(px - prx * 0.42, py - pry * 0.46, hr, hr), fill=WHITE)
        d.ellipse(xf.box(px + prx * 0.38, py + pry * 0.40, hr * 0.52, hr * 0.52),
                  fill=(255, 255, 255, 235))
        if kind == "half":
            # 上眼睑
            d.arc(xf.box(ex, ey, rx, ry), 190, 350, fill=DARK, width=xf.w(6.5))
        if kind == "sad":
            d.arc(xf.box(ex, ey - ry * 0.52, rx, ry * 0.9), 195, 345,
                  fill=DARK, width=xf.w(5.5))
        if kind == "angry":
            d.arc(xf.box(ex, ey - ry * 0.55, rx, ry), 195, 345,
                  fill=BRAND_LO, width=xf.w(7))
    elif kind in ("happy", "closed"):
        # ∩ 开心眯眼；∪ 睡觉/眨眼闭合
        box = xf.box(ex, ey, rx * 0.92, ry * 0.60)
        a0, a1 = (200, 340) if kind == "happy" else (20, 160)
        d.arc(box, a0, a1, fill=DARK, width=xf.w(6.6))
        if kind == "happy":
            for sx_, sy_ in ((-1, 1), (1, 1)):
                p0 = xf.p(ex + sx_ * rx * 0.92, ey - ry * 0.12)
                p1 = xf.p(ex + sx_ * (rx * 0.92 + 8), ey - ry * 0.30)
                d.line([p0, p1], fill=DARK, width=xf.w(4))
    elif kind == "love":
        hp = xf.poly(heart_points(ex, ey, rx * 1.02))
        d.polygon(hp, fill=(255, 92, 138))
        d.line(hp + [hp[0]], fill=DARK, width=xf.w(4.6), joint="curve")
        d.ellipse(xf.box(ex - rx * 0.34, ey - ry * 0.40, rx * 0.18, rx * 0.18),
                  fill=(255, 255, 255, 240))
    elif kind == "squeeze":
        # >< 用力眯眼
        if ex < CX:
            round_line(d, xf, (ex + rx * 0.55, ey - ry * 0.5), (ex - rx * 0.5, ey),
                       xf.w(6.8), DARK)
            round_line(d, xf, (ex - rx * 0.5, ey), (ex + rx * 0.55, ey + ry * 0.5),
                       xf.w(6.8), DARK)
        else:
            round_line(d, xf, (ex - rx * 0.55, ey - ry * 0.5), (ex + rx * 0.5, ey),
                       xf.w(6.8), DARK)
            round_line(d, xf, (ex + rx * 0.5, ey), (ex - rx * 0.55, ey + ry * 0.5),
                       xf.w(6.8), DARK)
    elif kind == "dizzy":
        d.ellipse(sclera, fill=WHITE, outline=DARK, width=ow)
        # 蚊香眼
        for k in range(2):
            rr = rx * (0.62 - k * 0.28)
            d.arc(xf.box(ex + rx * 0.12, ey, rr, rr * 1.08),
                  0 if k == 0 else 200, 330 if k == 0 else 520,
                  fill=DARK, width=xf.w(4.6))
    elif kind == "wink":
        box = xf.box(ex, ey, rx * 0.92, ry * 0.60)
        d.arc(box, 200, 340, fill=DARK, width=xf.w(6.6))


def draw_eyes(d, xf, kind, r=1.0, look=(0.0, 0.0), wink_side=None):
    for ex in (EYE_L[0], EYE_R[0]):
        if kind == "wink" and wink_side is not None:
            k = kind if abs(ex - (EYE_L[0] if wink_side == "l" else EYE_R[0])) < 1 else "happy"
            draw_eye(d, xf, ex, EYE_L[1], k if k != "wink" else ("wink" if ex == (EYE_L[0] if wink_side == "l" else EYE_R[0]) else "open"))
            continue
        out = 1.14 if kind == "surprise" else 1.0
        draw_eye(d, xf, ex, EYE_L[1], kind, r=r, look=look, out=out)


def draw_brows(d, xf, kind):
    y = 268
    if kind == "angry":
        round_line(d, xf, (EYE_L[0] - 32, y - 22), (EYE_L[0] + 28, y + 4), xf.w(6.5), DARK)
        round_line(d, xf, (EYE_R[0] + 32, y - 22), (EYE_R[0] - 28, y + 4), xf.w(6.5), DARK)
    elif kind == "sad":
        round_line(d, xf, (EYE_L[0] - 32, y + 20), (EYE_L[0] + 28, y - 8), xf.w(7.5), DARK)
        round_line(d, xf, (EYE_R[0] + 32, y + 20), (EYE_R[0] - 28, y - 8), xf.w(7.5), DARK)
    elif kind == "think":
        round_line(d, xf, (EYE_L[0] - 30, y + 8), (EYE_L[0] + 28, y - 6), xf.w(7), DARK)
        round_line(d, xf, (EYE_R[0] + 30, y + 2), (EYE_R[0] - 28, y - 12), xf.w(7), DARK)
    elif kind == "surprise":
        d.arc(xf.box(EYE_L[0], y - 8, 28, 16), 200, 340, fill=DARK, width=xf.w(5.5))
        d.arc(xf.box(EYE_R[0], y - 8, 28, 16), 200, 340, fill=DARK, width=xf.w(5.5))


def draw_mouth(d, xf, kind, op=0.0):
    mx, my = MOUTH_P
    w = xf.w(5.2)
    if kind == "smile":
        d.arc(xf.box(mx, my - 6, 25, 20), 20, 160, fill=DARK, width=w)
    elif kind == "cat":
        for sx_ in (-1, 1):
            d.arc(xf.box(mx + sx_ * 17, my, 18, 16),
                  20 if sx_ < 0 else 160, 160 if sx_ < 0 else 300,
                  fill=DARK, width=w)
    elif kind == "flat":
        round_line(d, xf, (mx - 16, my + 2), (mx + 16, my + 2), xf.w(5.5), DARK)
    elif kind == "frown":
        d.arc(xf.box(mx, my + 4, 22, 16), 200, 340, fill=DARK, width=w)
    elif kind in ("open", "open_smile", "open_big"):
        base_rx = 26 if kind != "open_big" else 31
        rx = base_rx
        ry = (6 + 22 * op) if kind != "open_big" else (8 + 26 * op)
        box = xf.box(mx, my + ry * 0.15, rx, ry)
        d.ellipse(box, fill=MOUTH, outline=DARK, width=xf.w(5.2))
        # 舌头
        tx, ty = mx, my + ry * 0.55
        d.ellipse(xf.box(tx, ty, rx * 0.58, ry * 0.42), fill=TONGUE)
    elif kind == "o":
        rx, ry = 10 + 6 * op, 13 + 8 * op
        d.ellipse(xf.box(mx, my + 2, rx, ry), fill=MOUTH, outline=DARK, width=w)
    elif kind == "chew":
        rx, ry = 20, 8 + 14 * op
        d.ellipse(xf.box(mx, my + 3, rx, ry), fill=MOUTH, outline=DARK, width=w)
        d.ellipse(xf.box(mx, my + 3 + ry * 0.55, rx * 0.55, ry * 0.4), fill=TONGUE)


def draw_blush(d, xf, strength=0.55, wide=1.0):
    if strength <= 0:
        return
    a = int(140 * min(1.0, strength))
    for bx in (CX - 88, CX + 88):
        rx, ry = 27 * wide, 15 * wide
        d.ellipse(xf.box(bx, 386, rx, ry), fill=BLUSH + (a,))
        for i in (-1, 0, 1):
            p0 = xf.p(bx + i * 9 - 3, 392)
            p1 = xf.p(bx + i * 9 + 3, 379)
            d.line([p0, p1], fill=(255, 96, 138, min(210, a + 60)), width=xf.w(2.6))


def draw_wave_fx(d, xf, t=0.0):
    """挥手状态：尾鳍左右摆动 + 外侧运动弧线（尾巴是蓝鲸 logo 的记忆点）。"""
    for k, (rad, ry, cy0) in enumerate(((24, 30, 242), (32, 40, 214))):
        ph = (t + k * 0.35) % 1.0
        ox = 10 * math.sin(ph * math.tau)
        cx, cy = xf.p(446 + ox, cy0)
        d.arc([cx - rad, cy - ry, cx + rad, cy + ry], 268, 60,
              fill=DARK, width=xf.w(3.6))
    # 尾鳍旁一颗小星星，更活泼
    d.polygon(xf.poly(star4_points(436, 176, 10)), fill=YELLOW,
              outline=DARK, width=xf.w(2.2))


def draw_music_note(d, xf, x, y, sc=1.0):
    """程序化绘制八分音符（避免字体缺字形）。"""
    d.ellipse(xf.box(x, y, 13 * sc, 9.5 * sc), fill=(238, 244, 255),
              outline=DARK, width=xf.w(2.6))
    round_line(d, xf, (x + 12 * sc, y - 3 * sc), (x + 12 * sc, y - 44 * sc),
               xf.w(3.2), (238, 244, 255))
    d.arc(xf.box(x + 2 * sc, y - 52 * sc, 16 * sc, 14 * sc), 300, 60,
          fill=DARK, width=xf.w(3.4))


def draw_extras(d, xf, names, t=0.0):
    for name in names:
        if name == "zzz":
            for k, (x, y, sz) in enumerate(((306, 196, 26), (336, 174, 20), (358, 156, 15))):
                f = xf.font(sz)
                px, py = xf.p(x, y)
                d.text((px, py), "Z", font=f, fill=(238, 244, 255, 255),
                       stroke_width=xf.w(2.4), stroke_fill=DARK, anchor="mm")
        elif name == "think":
            for k, (x, y, rr) in enumerate(((322, 214, 9), (348, 190, 11), (372, 168, 14))):
                d.ellipse(xf.box(x, y, rr, rr), fill=WHITE, outline=DARK,
                          width=xf.w(3.6))
        elif name == "sparkle":
            for (x, y, rr) in ((126, 292, 17), (334, 268, 12), (300, 190, 9)):
                d.polygon(xf.poly(star4_points(x, y, rr)), fill=YELLOW,
                          outline=DARK, width=xf.w(2.0))
                d.polygon(xf.poly(star4_points(x, y, rr * 0.45)), fill=WHITE)
        elif name == "hearts":
            for (x, y, rr) in ((306, 238, 13), (332, 210, 10), (352, 186, 7.5)):
                hp = xf.poly(heart_points(x, y, rr))
                d.polygon(hp, fill=(255, 96, 142))
                d.line(hp + [hp[0]], fill=DARK, width=xf.w(2.6), joint="curve")
        elif name == "tear":
            for (x, y, rr) in ((163, 372, 8), (198, 386, 6)):
                d.polygon(xf.poly(drop_points(x, y, rr)), fill=TEAR,
                          outline=DARK, width=xf.w(2.4))
        elif name == "tears_of_joy":
            for (x, y, rr) in ((163, 352, 7), (301, 352, 7)):
                d.polygon(xf.poly(drop_points(x, y, rr)), fill=TEAR,
                          outline=DARK, width=xf.w(2.2))
        elif name == "sweat":
            d.polygon(xf.poly(drop_points(316, 282, 11)), fill=TEAR,
                      outline=DARK, width=xf.w(2.8))
        elif name == "anger":
            cx, cy = 322, 196
            for a in range(4):
                ang = math.radians(45 + a * 90)
                p0 = (cx + math.cos(ang) * 4, cy + math.sin(ang) * 4)
                p1 = (cx + math.cos(ang) * 15, cy + math.sin(ang) * 15)
                round_line(d, xf, p0, p1, xf.w(5.0), (255, 70, 92))
        elif name == "excl":
            ex, ey = 348, 202
            d.rounded_rectangle(xf.box(ex, ey - 8, 7.5, 20), radius=xf.w(7),
                                fill=(255, 230, 110), outline=DARK,
                                width=xf.w(3.0))
            d.ellipse(xf.box(ex, ey + 26, 7.5, 7.5),
                      fill=(255, 230, 110), outline=DARK, width=xf.w(3.0))
        elif name == "music":
            draw_music_note(d, xf, 398, 172, 1.0)
        elif name == "cheeks":
            for bx in (CX - 106, CX + 106):
                d.ellipse(xf.box(bx, 380, 24, 20), fill=(255, 160, 186, 130))
        elif name == "crumbs":
            for (x, y, rr) in ((292, 428, 4), (312, 444, 3), (270, 448, 3)):
                d.ellipse(xf.box(x, y, rr, rr), fill=(255, 214, 150),
                          outline=DARK, width=xf.w(1.4))


# ---------------------------------------------------------------- 表情参数
def params(state, f, n):
    """返回单帧表情参数。"""
    p = dict(squash="N", eyes="open", eye_r=1.0, look=(0.0, 0.0),
             mouth="smile", op=0.0, brows=None, blush=0.55, extras=[],
             fin=False, wink=None, bob=0)
    t = f / max(1, n)
    if state == "idle":
        p["squash"] = ("Q1", "N", "S1", "N")[f % 4]
        p["bob"] = (0, -3, 0, -1)[f % 4]
        p["mouth"] = ("smile", "smile", "cat", "smile")[f % 4]
        p["blush"] = 0.5
    elif state == "blink":
        p["eyes"] = ("open", "half", "closed")[f]
        p["mouth"] = "cat"
    elif state == "happy":
        p["eyes"] = "happy"
        p["mouth"] = "open_smile"
        p["op"] = 0.55
        p["squash"] = ("N", "S1", "N")[f]
        p["bob"] = (0, -4, 0)[f]
        p["blush"] = 0.8
        p["extras"] = ["sparkle"] if f == 1 else []
    elif state == "laugh":
        p["eyes"] = "happy"
        p["mouth"] = "open_big"
        p["op"] = (0.7, 1.0, 0.6)[f]
        p["squash"] = ("Q2", "N", "Q1")[f]
        p["bob"] = (0, -3, 0)[f]
        p["blush"] = 0.95
        p["extras"] = ["tears_of_joy"]
    elif state == "talk":
        p["mouth"] = "open"
        p["op"] = (0.25, 0.7, 1.0)[f]
        p["squash"] = ("N", "Q1", "N")[f]
        p["bob"] = (0, -2, 0)[f]
        p["eyes"] = "open"
        p["look"] = (0.0, -0.1)
    elif state == "think":
        p["eyes"] = "look_up"
        p["look"] = (0.35, -0.45)
        p["mouth"] = "flat"
        p["squash"] = ("N", "S1", "N")[f]
        p["bob"] = (0, -2, 0)[f]
        p["brows"] = "think"
        p["extras"] = ["think"] if f >= 1 else []
        p["blush"] = 0.4
    elif state == "sleep":
        p["eyes"] = "closed"
        p["mouth"] = "o"
        p["op"] = 0.15
        p["squash"] = ("Q1", "N", "Q1")[f]
        p["bob"] = (0, -1, 0)[f]
        p["extras"] = ["zzz"]
        p["blush"] = 0.5
    elif state == "surprise":
        p["eyes"] = "surprise"
        p["mouth"] = "o"
        p["op"] = (0.6, 0.9)[f]
        p["squash"] = ("S2", "S1")[f]
        p["bob"] = (-3, -1)[f]
        p["brows"] = "surprise"
        p["extras"] = ["sweat", "excl"]
        p["blush"] = 0.45
    elif state == "sad":
        p["eyes"] = "sad"
        p["mouth"] = "frown"
        p["squash"] = ("Q1", "S1")[f]
        p["bob"] = (0, -2)[f]
        p["brows"] = "sad"
        p["extras"] = ["tear"]
        p["blush"] = 0.3
    elif state == "angry":
        p["eyes"] = "angry"
        p["mouth"] = "frown"
        p["squash"] = ("Q2", "Q1")[f]
        p["bob"] = (0, -2)[f]
        p["brows"] = "angry"
        p["extras"] = ["anger", "cheeks"]
        p["blush"] = 0.85
    elif state == "love":
        p["eyes"] = "love"
        p["mouth"] = "open_smile"
        p["op"] = 0.5
        p["squash"] = ("S1", "N")[f]
        p["bob"] = (0, -3)[f]
        p["extras"] = ["hearts"]
        p["blush"] = 1.0
    elif state == "drag":
        p["eyes"] = ("squeeze", "dizzy")[f]
        p["mouth"] = "open_big"
        p["op"] = 0.8
        p["squash"] = ("Q1", "N")[f]
        p["bob"] = (-2, 0)[f]
        p["extras"] = ["sweat"]
        p["blush"] = 0.75
    elif state == "wave":
        p["eyes"] = "wink"
        p["wink"] = "r"
        p["mouth"] = "open_smile"
        p["op"] = 0.5
        p["squash"] = ("Q1", "S1", "Q1")[f]
        p["bob"] = (-2, -4, -2)[f]
        p["fin"] = True
        p["extras"] = []
        p["blush"] = 0.8
    elif state == "eat":
        p["mouth"] = "chew"
        p["op"] = (0.9, 0.15, 1.0)[f]
        p["squash"] = ("Q2", "N", "Q1")[f]
        p["bob"] = (0, -2, 0)[f]
        p["blush"] = 0.8
        p["extras"] = ["cheeks", "crumbs"] if f == 1 else ["cheeks"]
        p["eyes"] = "open"
        p["look"] = (0.0, 0.12)
    return p


def render_frame(state, f, n):
    p = params(state, f, n)
    xf = mascot_xf(p["squash"])
    base = body_layer(p["squash"]).copy()

    face = Image.new("RGBA", (CW, CW), (0, 0, 0, 0))
    d = ImageDraw.Draw(face)

    if p["fin"]:
        draw_wave_fx(d, xf, t=f / max(1, n))
    draw_blush(d, xf, p["blush"])
    if p["brows"]:
        draw_brows(d, xf, p["brows"])
    if p["wink"]:
        # 眨眼侧用 happy 眯眯眼，另一侧正常
        draw_eye(d, xf, EYE_L[0], EYE_L[1], "happy" if p["wink"] == "l" else "open")
        draw_eye(d, xf, EYE_R[0], EYE_R[1], "happy" if p["wink"] == "r" else "open")
    else:
        draw_eyes(d, xf, p["eyes"], r=p["eye_r"], look=p["look"])
    draw_mouth(d, xf, p["mouth"], p["op"])
    draw_extras(d, xf, p["extras"]) if p["extras"] else None

    face512 = face.resize((S, S), Image.LANCZOS)
    bob = int(p.get("bob", 0))
    if bob:
        # 整体上下浮动（四周留白足够，offset 回绕不会带入可见像素）
        out = ImageChops.offset(base, 0, bob)
        out.alpha_composite(ImageChops.offset(face512, 0, bob))
    else:
        out = base
        out.alpha_composite(face512)
    return out


# ---------------------------------------------------------------- 图标
def _geom_bbox():
    """角色外接框（角色坐标，含描边），供图标按比例铺满画布。"""
    xs, ys = [], []
    for (x, y) in list(BODY) + list(TAIL_POLY):
        xs.append(x)
        ys.append(y)
    for (x, y, rx, ry, ang) in FIN_PARTS:
        th = math.radians(ang)
        ex = math.sqrt((rx * math.cos(th)) ** 2 + (ry * math.sin(th)) ** 2)
        ey = math.sqrt((rx * math.sin(th)) ** 2 + (ry * math.cos(th)) ** 2)
        xs += [x - ex, x + ex]
        ys += [y - ey, y + ey]
    p = OUTLINE_PX
    return (min(xs) - p, min(ys) - p, max(xs) + p, max(ys) + p)


ICON_BBOX = _geom_bbox()  # 角色外接框（角色坐标，含描边）


TAIL_PIVOT = (344, 344)   # 图标里尾巴放大时的支点


def icon_tail(k):
    px, py = TAIL_PIVOT
    return [(px + (x - px) * k, py + (y - py) * k) for (x, y) in TAIL_POLY]


def _icon_bbox(tail_pts):
    """角色外接框（角色坐标，含描边），供图标按比例铺满画布。"""
    xs, ys = [], []
    for (x, y) in list(BODY) + list(tail_pts):
        xs.append(x)
        ys.append(y)
    for (x, y, rx, ry, ang) in FIN_PARTS:
        th = math.radians(ang)
        ex = math.sqrt((rx * math.cos(th)) ** 2 + (ry * math.sin(th)) ** 2)
        ey = math.sqrt((rx * math.sin(th)) ** 2 + (ry * math.cos(th)) ** 2)
        xs += [x - ex, x + ex]
        ys += [y - ey, y + ey]
    p = OUTLINE_PX
    return (min(xs) - p, min(ys) - p, max(xs) + p, max(ys) + p)


def render_icon_at(size, supersample=8, detail=True, margin=None):
    """直接按目标尺寸渲染图标（原生像素级线宽，16px 也可辨识）。"""
    if margin is None:
        margin = 0.012 if size <= 24 else 0.03
    supersample = min(supersample, max(2, 1024 // max(1, size)))
    cs = size * supersample
    avail = cs * (1.0 - 2 * margin)
    tail_pts = icon_tail(1.12 if size <= 64 else 1.06)
    bx0, by0, bx1, by1 = _icon_bbox(tail_pts)
    bw, bh = bx1 - bx0, by1 - by0
    scale = min(avail / bw, avail / bh)
    ox = (cs - bw * scale) / 2 - bx0 * scale
    oy = (cs - bh * scale) / 2 - by0 * scale
    bxf = Xf(scale, ox=ox, oy=oy)

    # 小尺寸：放大眼睛，保证 16px 可辨识
    small = 1.0 - min(1.0, max(0.0, (size - 16) / 112.0))  # 16→1, 128→0
    tiny = size <= 24
    eye_r = 1.55 if tiny else 1.0 + 0.32 * small
    outline_final = max(1.0, size * (0.019 + 0.014 * small))
    outline_canvas = outline_final * supersample
    k_grow = max(1, int(round(outline_canvas)))

    mask = Image.new("L", (cs, cs), 0)
    dm = ImageDraw.Draw(mask)
    dm.polygon(bxf.poly(BODY), fill=255)
    dm.polygon(bxf.poly(tail_pts), fill=255)
    for (x, y, rx, ry, ang) in FIN_PARTS:
        stamp_ellipse(mask, bxf, x, y, rx, ry, ang)
    grown = dilate_fast(mask, k_grow)
    img = Image.new("RGBA", (cs, cs), DARK + (0,))
    img.paste(Image.new("RGBA", (cs, cs), DARK + (255,)), (0, 0), grown)

    # 渐变填充
    g = Image.new("RGBA", (1, cs))
    for y in range(cs):
        t = y / (cs - 1)
        c = mix(BRAND_HI, BRAND, t / 0.45) if t < 0.45 else mix(BRAND, BRAND_LO, (t - 0.45) / 0.55)
        g.putpixel((0, y), c + (255,))
    img.paste(g.resize((cs, cs), Image.BILINEAR), (0, 0), mask)
    # 内侧亮/暗边
    if size >= 48:
        rim = ImageChops.multiply(inner_rim(mask, k_grow * 0.8, k_grow * 0.8), mask)
        img.paste(Image.new("RGBA", (cs, cs), BRAND_HI + (200,)), (0, 0), rim)
        rim2 = ImageChops.multiply(inner_rim(mask, -k_grow * 0.8, -k_grow * 0.8), mask)
        img.paste(Image.new("RGBA", (cs, cs), BRAND_LO + (190,)), (0, 0), rim2)

    if detail:
        bm = Image.new("L", (cs, cs), 0)
        ImageDraw.Draw(bm).polygon(bxf.poly(BELLY_PTS), fill=255)
        bm = ImageChops.multiply(bm, mask)
        img.paste(Image.new("RGBA", (cs, cs), BELLY + (255,)), (0, 0), bm)

    # 面部（睁眼大眼 + 微笑：白眼球在小尺寸也清晰可读）
    face = Image.new("RGBA", (cs, cs), (0, 0, 0, 0))
    fd = ImageDraw.Draw(face)
    eye_y = 318
    rx = EYE_RX * eye_r
    ry = EYE_RY * eye_r
    stroke = max(1, int(round(2.6 * scale)))
    for ex in (EYE_L[0], EYE_R[0]):
        if tiny:
            # 16~24px：去掉眼睛描边，纯白色眼白 + 深色瞳孔，对比最强
            fd.ellipse(bxf.box(ex, eye_y, rx, ry), fill=WHITE)
            fd.ellipse(bxf.box(ex + 1, eye_y + 4, rx * 0.56, ry * 0.60), fill=DARK)
        else:
            fd.ellipse(bxf.box(ex, eye_y, rx, ry), fill=WHITE,
                       outline=DARK, width=stroke)
            fd.ellipse(bxf.box(ex + 1, eye_y + 5, rx * 0.52, ry * 0.56), fill=DARK)
            fd.ellipse(bxf.box(ex - rx * 0.28, eye_y - ry * 0.30,
                               max(2.0, rx * 0.24), max(2.0, rx * 0.24)),
                       fill=WHITE)
    # 微笑
    mbox = bxf.box(CX, 392, 22 * eye_r, 15 * eye_r)
    fd.arc(mbox, 20, 160, fill=DARK, width=max(1, int(round(2.8 * scale))))
    # 腮红
    if size >= 32:
        for bx in (CX - 88, CX + 88):
            fd.ellipse(bxf.box(bx, 384, 24, 13), fill=BLUSH + (150,))
    face = face.resize((size, size), Image.LANCZOS)
    out = img.resize((size, size), Image.LANCZOS)
    out.alpha_composite(face)
    return out


def write_ico(path, images):
    """手写 ICO 容器（内嵌 PNG 帧），保留各尺寸独立渲染质量。"""
    entries = b""
    data = b""
    offset = 6 + 16 * len(images)
    for size, im in images:
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        png = buf.getvalue()
        w = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(png),
                              offset + len(data))
        data += png
    path.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + entries + data)


# ---------------------------------------------------------------- SVG 图标
def _svg_path(pts, scale=1.0):
    d = "M " + " L ".join(f"{x * scale:.1f},{y * scale:.1f}" for x, y in pts) + " Z"
    return d


def build_svg():
    body = _svg_path(BODY)
    belly = _svg_path(BELLY_PTS)
    tail_shapes = [f'<path d="{_svg_path(TAIL_POLY)}"/>']
    fin_shapes = []
    for (x, y, rx, ry, ang) in FIN_PARTS:
        fin_shapes.append(
            f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" '
            f'transform="rotate({-ang} {x} {y})"/>')
    eye = []
    for ex in (EYE_L[0], EYE_R[0]):
        eye.append(
            f'<ellipse cx="{ex}" cy="{EYE_L[1]}" rx="31" ry="37" fill="#fff" '
            f'stroke="#0B1330" stroke-width="5"/>'
            f'<ellipse cx="{ex + 2}" cy="{EYE_L[1] + 4}" rx="17" ry="21" fill="#0B1330"/>'
            f'<circle cx="{ex - 6}" cy="{EYE_L[1] - 12}" r="7" fill="#fff"/>'
            f'<circle cx="{ex + 8}" cy="{EYE_L[1] + 12}" r="3.4" fill="#fff"/>')
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <title>蓝鲸桌宠 Blue Whale Pet</title>
  <desc>DeepSeek 蓝色大肥鱼非官方二创桌宠图标（程序化绘制）</desc>
  <defs>
    <linearGradient id="bodyBlue" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#708CFF"/>
      <stop offset="45%" stop-color="#4D6BFE"/>
      <stop offset="100%" stop-color="#2E44D0"/>
    </linearGradient>
  </defs>
  <!-- 描边层（先描边后填充，避免接缝） -->
  <g fill="#4D6BFE" stroke="#0B1330" stroke-width="14" stroke-linejoin="round">
    {''.join(tail_shapes)}
    {''.join(fin_shapes)}
    <path d="{body}"/>
  </g>
  <!-- 填充层 -->
  <g fill="url(#bodyBlue)" stroke="none">
    {''.join(tail_shapes)}
    {''.join(fin_shapes)}
    <path d="{body}"/>
  </g>
  <!-- 肚皮（呼应官方 logo 浅色负空间） -->
  <path d="{belly}" fill="#C6D8FF" opacity="0.95"/>
  <!-- 腮红 -->
  <ellipse cx="144" cy="386" rx="26" ry="14" fill="#FF7AA0" opacity="0.55"/>
  <ellipse cx="320" cy="386" rx="26" ry="14" fill="#FF7AA0" opacity="0.55"/>
  <!-- 眼睛 -->
  {''.join(eye)}
  <!-- 微笑 -->
  <path d="M 208,396 Q 232,414 256,396" fill="none" stroke="#0B1330"
        stroke-width="5.5" stroke-linecap="round"/>
</svg>
'''
    return svg


# ---------------------------------------------------------------- 安装器插画
def rounded_bg(w, h, top, bottom, radius=14):
    im = Image.new("RGBA", (w * 2, h * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w * 2 - 1, h * 2 - 1], radius=radius * 2, fill=top + (255,))
    grad = Image.new("RGBA", (1, h * 2))
    for y in range(h * 2):
        grad.putpixel((0, y), mix(top, bottom, y / (h * 2 - 1)) + (255,))
    mask = Image.new("L", (w * 2, h * 2), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w * 2 - 1, h * 2 - 1],
                                           radius=radius * 2, fill=255)
    im.paste(grad.resize((w * 2, h * 2), Image.BILINEAR), (0, 0), mask)
    return im.resize((w, h), Image.LANCZOS)


def draw_waves(d, w, h, color, count=3, alpha=38):
    for i in range(count):
        cy = h * (0.55 + i * 0.16)
        r = w * (0.55 + i * 0.18)
        box = [-r * 0.4, cy - r * 0.34, r * 1.4, cy + r * 0.34]
        d.arc(box, 190, 350, fill=color + (alpha,), width=max(2, h // 90))


def make_installer_assets():
    INSTALLER.mkdir(parents=True, exist_ok=True)
    # ---- banner 600×160（安装向导顶部横幅）
    W, H = 600, 160
    banner = rounded_bg(W, H, (12, 22, 62), (27, 44, 122), radius=0)
    deco = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    draw_waves(dd, W, H, (150, 180, 255), count=3, alpha=34)
    for (cx, cy, r, a) in ((520, 30, 90, 26), (70, 150, 60, 20), (460, 140, 40, 18)):
        dd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(120, 150, 255, a))
    banner.alpha_composite(deco)
    d = ImageDraw.Draw(banner)
    whale = render_icon_at(132, supersample=4, detail=True)
    banner.alpha_composite(whale, (16, (H - 132) // 2 + 4))
    f1 = load_font(46, bold=True)
    f2 = load_font(19)
    f3 = load_font(15)
    d.text((168, 30), "蓝鲸桌宠", font=f1, fill=(255, 255, 255, 255))
    d.text((170, 86), "Blue Whale Pet · DeepSeek 桌面宠物", font=f2,
           fill=(186, 203, 255, 255))
    d.text((170, 114), "蓝色大肥鱼 · v1.0.0", font=f3, fill=(140, 164, 226, 255))
    banner.save(INSTALLER / "banner.png")

    # ---- side 164×314（安装向导左侧竖幅）
    W, H = 164, 314
    side = rounded_bg(W, H, (12, 22, 62), (20, 34, 96), radius=0)
    deco2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd2 = ImageDraw.Draw(deco2)
    draw_waves(dd2, W, H, (150, 180, 255), count=3, alpha=30)
    side.alpha_composite(deco2)
    d = ImageDraw.Draw(side)
    whale = render_icon_at(118, supersample=4, detail=True)
    side.alpha_composite(whale, ((W - 118) // 2, 18))
    f1 = load_font(34, bold=True)
    f2 = load_font(14)
    for i, ch in enumerate("蓝鲸桌宠"):
        d.text((W // 2, 156 + i * 38), ch, font=f1, fill=(255, 255, 255, 255),
               anchor="mm")
    d.text((W // 2, 300), "v1.0.0", font=f2, fill=(150, 172, 230, 255),
           anchor="mm")
    side.save(INSTALLER / "side.png")

    # ---- setup.ico（SPEC 在 installer/，同时复制到 icons/ 便于打包脚本统一引用）
    imgs = [(s, render_icon_at(s, supersample=8, detail=(s >= 48)))
            for s in (16, 24, 32, 48, 64, 128, 256)]
    write_ico(INSTALLER / "setup.ico", imgs)
    ICONS.mkdir(parents=True, exist_ok=True)
    write_ico(ICONS / "setup.ico", imgs)


# ---------------------------------------------------------------- 图标产出
def make_icons():
    ICONS.mkdir(parents=True, exist_ok=True)
    app_sizes = (256, 128, 64, 48, 32, 16)
    write_ico(ICONS / "app.ico",
              [(s, render_icon_at(s, supersample=8, detail=True)) for s in app_sizes])
    app512 = render_icon_at(512, supersample=2, detail=True)
    app512.save(ICONS / "app.png")
    write_ico(ICONS / "tray.ico",
              [(s, render_icon_at(s, supersample=8, detail=False))
               for s in (16, 32, 48)])
    (ICONS / "blue-whale-pet.svg").write_text(build_svg(), encoding="utf-8")
    for n in (16, 24, 32, 48, 64, 128, 256, 512):
        p = ICONS / "hicolor" / f"{n}x{n}" / "apps"
        p.mkdir(parents=True, exist_ok=True)
        render_icon_at(n, supersample=max(2, 1024 // n), detail=(n >= 48)).save(
            p / "blue-whale-pet.png")


# ---------------------------------------------------------------- 主精灵
def make_mascot():
    MASTER.mkdir(parents=True, exist_ok=True)
    # 清掉旧帧避免残留
    for old in MASTER.glob("*.png"):
        try:
            old.unlink()
        except OSError:
            pass
    manifest = {
        "version": 1,
        "canvas": {"w": S, "h": S, "anchor_x": ANCHOR[0], "anchor_y": ANCHOR[1]},
        "key_color": KEY,
        "default_state": "idle",
        "states": {},
    }
    for state, (n, durs, loop) in STATES.items():
        names = []
        for f in range(n):
            img = render_frame(state, f, n)
            name = f"{state}_{f}"
            save_png(img, MASTER / f"{name}.png")
            names.append(name)
        manifest["states"][state] = {"frames": names,
                                     "durations": list(durs),
                                     "loop": bool(loop)}
    (A / "mascot" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


# ---------------------------------------------------------------- 表情总览
def make_contact_sheet(manifest=None):
    PREVIEW.mkdir(parents=True, exist_ok=True)
    if manifest is None:
        manifest = json.loads((A / "mascot" / "manifest.json").read_text(encoding="utf-8"))
    cols = 5
    cell = 118
    left = 132
    top = 116
    row_h = cell + 26
    width = left + cols * (cell + 8) + 24
    height = top + len(STATES) * row_h + 54
    sheet = Image.new("RGBA", (width, height), (16, 26, 66, 255))
    deco = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    for (cx, cy, r, a) in ((width - 90, 70, 120, 26), (60, height - 60, 110, 22),
                           (width // 2, height // 2, 280, 14)):
        dd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(120, 150, 255, a))
    sheet.alpha_composite(deco)
    d = ImageDraw.Draw(sheet)
    f_title = load_font(34, bold=True)
    f_sub = load_font(16)
    f_state = load_font(21, bold=True)
    f_small = load_font(13)
    d.text((24, 26), "蓝鲸桌宠 · 蓝色大肥鱼 表情总览", font=f_title,
           fill=(255, 255, 255, 255))
    d.text((26, 72), f"14 states / {sum(len(v['frames']) for v in manifest['states'].values())} frames"
                     f" · 512×512 RGBA · 锚点(256,496) · 品牌蓝 #4D6BFE", font=f_sub,
           fill=(176, 196, 255, 255))
    for row, state in enumerate(STATES):
        st = manifest["states"][state]
        y = top + row * row_h
        d.text((24, y + cell // 2 - 16), STATE_ZH[state], font=f_state,
               fill=(255, 255, 255, 255))
        d.text((24, y + cell // 2 + 8), state, font=f_small, fill=(150, 176, 240, 255))
        for col, name in enumerate(st["frames"][:cols]):
            im = Image.open(MASTER / f"{name}.png").convert("RGBA")
            th = im.resize((cell, cell), Image.LANCZOS)
            x = left + col * (cell + 8)
            d.rounded_rectangle([x - 3, y - 3, x + cell + 3, y + cell + 18],
                                radius=10, fill=(32, 44, 94, 255))
            sheet.alpha_composite(th, (x, y))
            d.text((x + cell // 2, y + cell + 6), f"{name}", font=f_small,
                   fill=(150, 176, 240, 220), anchor="mm")
    sheet.convert("RGBA").save(PREVIEW / "contact_sheet.png")
    return PREVIEW / "contact_sheet.png"


# ---------------------------------------------------------------- 压缩保存
FRAME_LIMIT = 60 * 1024  # 单帧 PNG 体积上限（SPEC / 用户要求）


def posterize_rgba(img, bits):
    """按位降低 RGB 色深（保留 alpha），提升 PNG 压缩率。"""
    step = 1 << (8 - bits)
    lut = [min(255, (v // step) * step + step // 2) for v in range(256)]
    r, g, b, a = img.split()
    return Image.merge("RGBA", (r.point(lut), g.point(lut), b.point(lut), a))


SAVE_PREFER = 48 * 1024   # 优先不超过 48KB（给不同帧留余量）


def save_png(img, path):
    """保存 RGBA PNG：优先 6bit 色深（肉眼无损），体积超标再逐级降低。"""
    last = 0
    for bits in (8, 6, 5, 4):
        im = img if bits == 8 else posterize_rgba(img, bits)
        im.save(path, compress_level=9)
        last = path.stat().st_size
        if last <= SAVE_PREFER:
            return last
    return last


# ---------------------------------------------------------------- 参考图分析
def extract_blue_alpha(im):
    """对浅色背景上的官方蓝鲸做色差键控（b-r 越大越不透明）。"""
    r, g, b = im.convert("RGB").split()
    diff = ImageChops.subtract(b, r)                      # 蓝-红通道差
    return diff.point(lambda v: 0 if v <= 12 else min(255, (v - 12) * 255 // 140))


def analyze_references():
    """对参考图做取色 / 抠图 / 比例分析，打印结果（可复现，无外部依赖）。"""
    from PIL import ImageStat
    refs = A / "source" / "references"
    print("[analyze] 参考图分析：")
    logo = refs / "deepseek-app-icon-vectorseek.png"
    if logo.exists():
        im = Image.open(logo)
        print(f"  官方 logo {logo.name}: {im.size}, mode={im.mode}")
        if im.mode in ("RGBA", "LA"):
            alpha = im.convert("RGBA").getchannel("A")
            rgb = im.convert("RGB")
        else:
            rgb = im.convert("RGB")
            alpha = extract_blue_alpha(rgb)
            print("  → 实际为 RGB 图：背景是烘焙的棋盘格（并非真透明），"
                  "用 b-r 色差键控抠出鲸鱼轮廓")
        mask = alpha.point(lambda v: 255 if v > 40 else 0)
        bbox = mask.getbbox()
        opaque = alpha.point(lambda v: 255 if v > 200 else 0)
        stat = ImageStat.Stat(rgb, opaque)
        avg = tuple(int(round(c)) for c in stat.mean)
        w = bbox[2] - bbox[0] if bbox else 0
        h = bbox[3] - bbox[1] if bbox else 0
        print(f"  键控抠图主体包围盒={bbox}, 宽高比={w / max(1, h):.2f}")
        print(f"  官方主体平均色 = #{avg[0]:02X}{avg[1]:02X}{avg[2]:02X}"
              f"（本资产品牌蓝 #{BRAND[0]:02X}{BRAND[1]:02X}{BRAND[2]:02X}）")
        # 保存抠图产物（透明背景，官方蓝），仅作参考
        cut = rgb.convert("RGBA")
        cut.putalpha(alpha)
        out = refs / "deepseek-logo-vectorseek-transparent.png"
        cut.save(out)
        print(f"  → 抠图参考已保存 {out.name}")
    ico = refs / "deepseek-favicon-225.ico"
    if ico.exists():
        im = Image.open(ico)
        print(f"  官网 favicon: {im.size}, mode={im.mode}, sizes={im.info.get('sizes')}")
    svg = refs / "deepseek-simpleicons.svg"
    if svg.exists():
        txt = svg.read_text(encoding="utf-8", errors="ignore")
        print(f"  simple-icons SVG: {len(txt)} 字符（单色 path，CC0-1.0）")
    social = refs / "deepseek-social-1200x630.jpg"
    if social.exists():
        im = Image.open(social).convert("RGB")
        alpha = extract_blue_alpha(im)
        bbox = alpha.point(lambda v: 255 if v > 40 else 0).getbbox()
        print(f"  官网社交图 {social.name}: {im.size}，logo 蓝色区域包围盒={bbox}")
    for p in sorted(refs.glob("*.webp")) + sorted(refs.glob("*.jpg")) + sorted(refs.glob("*.jpeg")):
        try:
            im = Image.open(p).convert("RGB")
            print(f"  网络参考 {p.name}: {im.size}（仅风格参考，成品不使用原图）")
        except Exception as e:  # noqa: BLE001
            print(f"  网络参考 {p.name}: 无法解析 ({e})")
    print(f"[analyze] 本资产角色轮廓：主体包围盒≈{tuple(round(v, 1) for v in ICON_BBOX)}，"
          f"宽高比={(ICON_BBOX[2] - ICON_BBOX[0]) / (ICON_BBOX[3] - ICON_BBOX[1]):.2f}")


# ---------------------------------------------------------------- 调试预览
def debug_frame(spec, out_path):
    state, _, fr = spec.partition(":")
    n = STATES[state][0]
    f = int(fr or 0) % n
    img = render_frame(state, f, n)
    Image.new("RGBA", img.size, (28, 34, 52, 255)).alpha_composite(img) \
        if False else None
    bg = Image.new("RGBA", img.size, (238, 241, 248, 255))
    bg.alpha_composite(img)
    bg.save(out_path)
    print(f"[debug] {state}_{f} -> {out_path}")


def debug_sheet(out_path):
    rows = []
    for state, (n, _, _) in STATES.items():
        rows.append([render_frame(state, f, n) for f in range(n)])
    big = Image.new("RGBA", (S * 5, S * len(rows)), (238, 241, 248, 255))
    for r, frames in enumerate(rows):
        for c, im in enumerate(frames):
            big.alpha_composite(im, (c * S, r * S))
    big.save(out_path)
    print(f"[debug] sheet -> {out_path}")


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="生成蓝鲸桌宠美术资产")
    ap.add_argument("--analyze", action="store_true", help="打印参考图取色/比例分析")
    ap.add_argument("--frame", help="调试：渲染单帧，如 idle:1")
    ap.add_argument("--out", help="调试：单帧输出路径")
    ap.add_argument("--sheet", help="调试：输出 14 表情原始拼图路径")
    ap.add_argument("--skip-icons", action="store_true")
    ap.add_argument("--skip-installer", action="store_true")
    args = ap.parse_args(argv)

    if args.analyze:
        analyze_references()
        if not args.frame and not args.sheet:
            return 0
    if args.frame:
        debug_frame(args.frame, args.out or "debug_frame.png")
        return 0
    if args.sheet:
        debug_sheet(args.sheet)
        return 0

    print("[gen] 生成主精灵 14 state ...")
    manifest = make_mascot()
    print(f"[gen] mascot: {sum(len(v['frames']) for v in manifest['states'].values())} 帧")
    if not args.skip_icons:
        print("[gen] 生成图标 ...")
        make_icons()
    if not args.skip_installer:
        print("[gen] 生成安装器插画 ...")
        make_installer_assets()
    print("[gen] 生成表情总览 ...")
    p = make_contact_sheet(manifest)
    print(f"[gen] 完成：{p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
