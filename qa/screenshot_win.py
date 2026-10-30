"""窗口截图/启动验证工具（Lead QA）。

在 Windows 真机桌面启动桌宠，定位其窗口（EnumWindows 按 PID），截图并检测画面中是否有蓝色宠物像素，
支持 --showcase 模式连续截图（用于文档展示）。

用法:
  py qa/screenshot_win.py --exe "release/windows/BlueWhalePet-Portable-1.0.0.exe" --out docs/screenshots
  py qa/screenshot_win.py --dev --out qa/out            # 用 py src/main.py 开发态
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from PIL import ImageGrab

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

ROOT = Path(__file__).resolve().parent.parent


def find_windows(pid: int) -> list[tuple[int, tuple[int, int, int, int]]]:
    out: list[tuple[int, tuple[int, int, int, int]]] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _lparam):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            out.append((hwnd, (r.left, r.top, r.right, r.bottom)))
        return True

    user32.EnumWindows(cb, 0)
    return out


def wait_windows(pid: int, timeout: float = 25.0) -> list[tuple[int, tuple[int, int, int, int]]]:
    t0 = time.time()
    while time.time() - t0 < timeout:
        wins = find_windows(pid)
        if wins:
            return wins
        time.sleep(0.3)
    return []


def blue_ratio(img) -> float:
    """画面中品牌蓝像素占比。"""
    im = img.convert("RGB").resize((160, 160))
    px = list(im.getdata())
    n = 0
    for r, g, b in px:
        if b > 120 and b > r + 30 and b > g + 20 and r < 150:
            n += 1
    return n / len(px)


def capture_region(box, path: Path, pad: int = 24) -> float:
    l, t, r, b = box
    x0, y0 = max(0, l - pad), max(0, t - pad)
    x1, y1 = r + pad, b + pad
    img = ImageGrab.grab(bbox=(x0, y0, x1, y1), all_screens=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return blue_ratio(img)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", help="便携 exe 或安装版 exe 路径")
    ap.add_argument("--dev", action="store_true", help="开发态: py src/main.py")
    ap.add_argument("--out", default=str(ROOT / "qa" / "out"))
    ap.add_argument("--frames", type=int, default=6, help="showcase 截图张数")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--seconds", type=float, default=14, help="showcase 时长")
    ap.add_argument("--no-showcase", action="store_true", help="只启动截图不展示表情循环")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = out / "qa-config.json"
    cfg.write_text(json.dumps({"pet": {"size": 240, "x": 120, "y": 240, "always_on_top": True}},
                              ensure_ascii=False), encoding="utf-8")
    if args.dev:
        cmd = [sys.executable, str(ROOT / "src" / "main.py"), "--config", str(cfg)]
        cwd = ROOT
    elif args.exe:
        cmd = [str(Path(args.exe).resolve()), "--config", str(cfg)]
        cwd = Path(args.exe).resolve().parent
    else:
        print("需要 --exe 或 --dev")
        return 2
    if not args.no_showcase:
        cmd += ["--showcase", str(args.seconds)]
    log = open(out / "launch.log", "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT)
    result = {"cmd": cmd, "pid": proc.pid, "windows": [], "shots": [], "ok": False}
    try:
        wins = wait_windows(proc.pid)
        result["windows"] = [{"hwnd": h, "rect": list(r)} for h, r in wins]
        if not wins:
            print("FAIL: 未找到可见窗口（进程可能崩溃，见 launch.log）")
            result["returncode"] = proc.poll()
            return 1
        # 取最大的窗口
        wins.sort(key=lambda w: (w[1][2] - w[1][0]) * (w[1][3] - w[1][1]), reverse=True)
        hwnd, box = wins[0]
        sizes = []
        for i in range(args.frames):
            p = out / f"pet_shot_{i:02d}.png"
            ratio = capture_region(box, p)
            sizes.append(ratio)
            result["shots"].append({"file": str(p), "blue_ratio": round(ratio, 4), "rect": list(box)})
            time.sleep(args.interval if i < args.frames - 1 else 0)
        result["blue_ratio_max"] = max(sizes) if sizes else 0
        result["ok"] = max(sizes) > 0.02
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)], capture_output=True)
        log.close()
    (out / "screenshot_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SCREENSHOT OK" if result.get("ok") else "SCREENSHOT FAIL")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
