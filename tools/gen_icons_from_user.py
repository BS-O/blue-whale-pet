# -*- coding: utf-8 -*-
"""用用户提供的 icon/ico.png 直接生成全套应用图标。

ico.png 是成品图标设计（306×306 RGBA）；≤256 档位由原图直接 LANCZOS 缩放
（不经放大，保持锐利）；512 档（app.png / hicolor-512）由 306 放大 + 轻锐化。
"""
from __future__ import annotations

import base64
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "assets" / "icons"
HICOLOR = ICONS / "hicolor"
SRC = Path(r"C:\Users\38495\Desktop\icon\ico.png")
ICO_SIZES = (256, 128, 64, 48, 32, 16)
HICO_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)


def main() -> None:
    src = Image.open(SRC).convert("RGBA")
    if src.width != src.height:
        side = min(src.size)
        src = src.crop(((src.width - side) // 2, (src.height - side) // 2,
                        (src.width + side) // 2, (src.height + side) // 2))
    ICONS.mkdir(parents=True, exist_ok=True)
    # ≤256：原图直出
    src.save(ICONS / "app.ico", sizes=[(s, s) for s in ICO_SIZES])
    src.save(ICONS / "setup.ico", sizes=[(s, s) for s in ICO_SIZES])
    src.save(ICONS / "tray.ico", sizes=[(48, 48), (32, 32), (16, 16)])
    for s in HICO_SIZES:
        if s <= 306:
            src.resize((s, s), Image.LANCZOS).save(HICOLOR / f"{s}x{s}" / "apps" / "blue-whale-pet.png")
    # 512：放大 + 轻锐化
    big = src.resize((512, 512), Image.LANCZOS).filter(
        ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
    big.save(ICONS / "app.png")
    big.save(HICOLOR / "512x512" / "apps" / "blue-whale-pet.png")
    # SVG（内嵌原尺寸 base64）
    b64 = base64.b64encode(Path(SRC).read_bytes()).decode()
    (ICONS / "blue-whale-pet.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {src.width} {src.height}">'
        f'<image width="{src.width}" height="{src.height}" href="data:image/png;base64,{b64}"/></svg>',
        encoding="utf-8")
    print(f"WROTE icons from {SRC.name} ({src.size}): app.ico/setup.ico/tray.ico/app.png/hicolor/svg")


if __name__ == "__main__":
    main()
