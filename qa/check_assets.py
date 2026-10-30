"""独立资产验收（Lead QA，不复用 asset-fish 的 checker）。

用法: py qa/check_assets.py [--project PATH]
校验: manifest 契约 / 帧尺寸模式 / alpha 包围盒与锚点一致性 / 图标尺寸集 / Linux hicolor / 安装器插画 / 预览图。
退出码 0 = 全绿。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

STATES = ["idle", "blink", "happy", "laugh", "talk", "think", "sleep", "surprise",
          "sad", "angry", "love", "drag", "wave", "eat"]
HICOLOR = [16, 24, 32, 48, 64, 128, 256, 512]
errors: list[str] = []
warnings: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--min-states", type=int, default=14)
    args = ap.parse_args()
    root = Path(args.project)
    assets = root / "assets"
    mpath = assets / "mascot" / "manifest.json"
    check(mpath.exists(), f"缺少 {mpath}")
    if errors:
        print("\n".join(errors))
        return 1
    m = json.loads(mpath.read_text(encoding="utf-8"))
    check(m.get("version") == 1, "manifest.version 必须为 1")
    canvas = m.get("canvas", {})
    cw, ch = canvas.get("w"), canvas.get("h")
    check((cw, ch) == (512, 512), f"canvas 必须 512x512, 实际 {cw}x{ch}")
    ax, ay = canvas.get("anchor_x"), canvas.get("anchor_y")
    check(ax == 256 and ay == 496, f"anchor 必须 (256,496), 实际 ({ax},{ay})")
    check(m.get("key_color", "").lower() == "#010203", f"key_color 必须 #010203, 实际 {m.get('key_color')}")
    states = m.get("states", {})
    check(len(states) >= args.min_states, f"state 数量 {len(states)} < {args.min_states}")
    for s in STATES:
        check(s in states, f"缺少必需 state: {s}")

    bboxes: list[tuple[str, tuple[int, int, int, int]]] = []
    total_frames = 0
    for name, spec in states.items():
        frames = spec.get("frames") or []
        durs = spec.get("durations") or []
        check(len(frames) >= 1, f"{name}: 无 frames")
        check(len(frames) == len(durs), f"{name}: frames/durations 长度不一致")
        check(all(isinstance(d, int) and d > 0 for d in durs), f"{name}: durations 非法 {durs}")
        for fr in frames:
            p = assets / "mascot" / "master" / f"{fr}.png"
            if not p.exists():
                errors.append(f"缺少帧文件 {p}")
                continue
            total_frames += 1
            im = Image.open(p)
            check(im.mode == "RGBA", f"{p.name}: mode={im.mode} 必须 RGBA")
            check(im.size == (512, 512), f"{p.name}: size={im.size} 必须 512x512")
            if im.mode != "RGBA":
                continue
            bbox = im.getchannel("A").getbbox()
            check(bbox is not None, f"{p.name}: alpha 全透明")
            if bbox is None:
                continue
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            check(w >= 260 and h >= 240, f"{p.name}: 角色过小 bbox={bbox}")
            check(bbox[3] <= 506, f"{p.name}: 底部越出画布 {bbox}")
            bboxes.append((name, bbox))
    # 锚点一致性：每个 state 的第一帧
    per_state = {}
    for name, bbox in bboxes:
        per_state.setdefault(name, bbox)
    for name, (x0, y0, x1, y1) in per_state.items():
        cx = (x0 + x1) / 2
        check(abs(cx - 256) <= 24, f"{name}: 水平锚点偏差 {cx - 256:.0f}px (>24)")
        check(abs(y1 - 496) <= 24, f"{name}: 底部锚点偏差 {y1 - 496}px (>24)")
    # 同 state 帧间抖动
    by_state: dict[str, list[tuple[int, int, int, int]]] = {}
    for name, bbox in bboxes:
        by_state.setdefault(name, []).append(bbox)
    for name, bs in by_state.items():
        if len(bs) < 2:
            continue
        base = bs[0]
        for b in bs[1:]:
            dy = abs(b[3] - base[3])
            dx = abs(((b[0] + b[2]) / 2) - ((base[0] + base[2]) / 2))
            check(dy <= 10 and dx <= 10, f"{name}: 帧间抖动过大 dx={dx:.0f} dy={dy}")

    # 图标
    def has_sizes(path: Path, sizes: set[int]) -> None:
        if not path.exists():
            errors.append(f"缺少图标 {path}")
            return
        try:
            im = Image.open(path)
            im.load()
            got = set()
            n = getattr(im, "n_frames", 1)
            for i in range(n):
                im.seek(i)
                got.add(im.size[0])
            check(sizes <= got, f"{path.name}: 尺寸集 {sorted(got)} 不含 {sorted(sizes - got)}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path.name}: 无法解析 ico ({exc})")

    ico = assets / "icons"
    has_sizes(ico / "app.ico", {256, 128, 64, 48, 32, 16})
    has_sizes(ico / "tray.ico", {16, 32})
    has_sizes(ico / "setup.ico", {16, 32, 48, 64, 128, 256})
    ap_png = ico / "app.png"
    if ap_png.exists():
        im = Image.open(ap_png)
        check(im.size == (512, 512) and im.mode == "RGBA", f"app.png 必须 512 RGBA, 实际 {im.size} {im.mode}")
    else:
        errors.append("缺少 assets/icons/app.png")
    check((ico / "blue-whale-pet.svg").exists(), "缺少 assets/icons/blue-whale-pet.svg")
    for s in HICOLOR:
        p = ico / "hicolor" / f"{s}x{s}" / "apps" / "blue-whale-pet.png"
        if not p.exists():
            errors.append(f"缺少 {p}")
            continue
        im = Image.open(p)
        check(im.size == (s, s), f"{p}: {im.size} != {s}x{s}")
    for name, size in [("banner.png", (600, 160)), ("side.png", (164, 314))]:
        p = assets / "installer" / name
        if not p.exists():
            errors.append(f"缺少 {p}")
            continue
        im = Image.open(p)
        check(im.size == size, f"{p}: {im.size} != {size}")
    sheet = assets / "preview" / "contact_sheet.png"
    if not sheet.exists():
        errors.append(f"缺少 {sheet}")
    # 体积
    total = sum(p.stat().st_size for p in assets.rglob("*") if p.is_file())
    if total > 9 * 1024 * 1024:
        warnings.append(f"assets 总体积 {total / 1024 / 1024:.1f}MB > 9MB，注意 exe 体积")
    print(f"states={len(states)} frames={total_frames} assets_size={total / 1024 / 1024:.2f}MB")
    for w in warnings:
        print(f"WARN {w}")
    if errors:
        print(f"\nFAIL {len(errors)} 项:")
        for e in errors:
            print(" -", e)
        return 1
    print("ASSETS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
