"""生成文档用截图（Lead QA）：先铺一层渐变色全屏背景，再启动桌宠/聊天/设置，截取各窗口。

用法:
  py qa/backdrop_shots.py --dev --out docs/screenshots           # hero + 表情 + 气泡
  py qa/backdrop_shots.py --exe release/windows/BlueWhalePet-Portable-1.0.0.exe --out docs/screenshots
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import subprocess
import sys
import time
from pathlib import Path

import tkinter as tk
from PIL import Image, ImageDraw, ImageGrab, ImageTk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import winproc  # noqa: E402

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()
ROOT = Path(__file__).resolve().parent.parent


def find_windows(pid: int):
    """pid 及其子进程（PyInstaller onefile GUI 在子进程）的可见窗口。"""
    return winproc.find_windows(winproc.family(pid))


def make_backdrop(root: tk.Tk, w: int, h: int) -> tk.PhotoImage:
    img = Image.new("RGB", (w, h))
    top, bottom = (238, 243, 255), (196, 212, 255)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(h - 1, 1)
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    # 右下角装饰圆
    d.ellipse([w - 420, h - 380, w + 40, h + 120], fill=(214, 226, 255))
    d.ellipse([-160, h - 260, 260, h + 120], fill=(224, 234, 255))
    photo = ImageTk.PhotoImage(img)
    cv = tk.Canvas(root, width=w, height=h, highlightthickness=0)
    cv.pack()
    cv.create_image(0, 0, image=photo, anchor="nw")
    return photo


def shot_region(box, out: Path, pad: int = 14) -> str:
    l, t, r, b = box
    user32.SetCursorPos(4, 4)
    time.sleep(0.2)
    img = ImageGrab.grab(bbox=(max(0, l - pad), max(0, t - pad), min(1919, r + pad), min(1079, b + pad)),
                         all_screens=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return str(out)


def run_scene(base_cmd: list[str], cwd: Path, extra: list[str], out: Path, label: str,
              wait: float, shots: int = 1, interval: float = 1.5, fullscreen: bool = False) -> dict:
    cmd = base_cmd + extra
    log = open(out / f"{label}.log", "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT)
    result = {"label": label, "cmd": cmd, "windows": [], "shots": []}
    try:
        time.sleep(wait)
        for i in range(shots):
            wins = find_windows(proc.pid)
            user32.SetCursorPos(4, 4)
            time.sleep(0.25)
            if fullscreen:
                img = ImageGrab.grab(bbox=(0, 0, 1920, 1080), all_screens=True)
                fp = out / f"{label}_full_{i:02d}.png"
                img.save(fp)
                result["shots"].append({"file": str(fp), "title": "__fullscreen__", "rect": [0, 0, 1920, 1080]})
            for w in wins:
                # 强制前置/重绘，避免被背景窗遮挡或未绘制导致空白截图
                user32.ShowWindow(w["hwnd"], 5)
                user32.SetForegroundWindow(w["hwnd"])
            time.sleep(0.35)
            wins = find_windows(proc.pid)
            for w in wins:
                title = w["title"]
                safe = "".join(ch for ch in title if ch.isalnum() or ch in "_-") or f"w{w['hwnd']}"
                name = f"{label}_{i:02d}_{safe}.png"
                result["shots"].append({"file": shot_region(w["rect"], out / name), "title": title, "rect": w["rect"]})
            time.sleep(interval)
        result["windows"] = find_windows(proc.pid)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=6)
        except Exception:  # noqa: BLE001
            winproc.kill_tree(proc.pid)
        winproc.kill_by_name("BlueWhalePet")
        log.close()
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe")
    ap.add_argument("--dev", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "docs" / "screenshots"))
    ap.add_argument("--mock", default="http://127.0.0.1:8765")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.dev:
        base = [sys.executable, str(ROOT / "src" / "main.py")]
        cwd = ROOT
    elif args.exe:
        base = [str(Path(args.exe).resolve())]
        cwd = Path(args.exe).resolve().parent
    else:
        print("需要 --exe 或 --dev")
        return 2
    cfg = (out / "shot-config.json").resolve()
    cfg.write_text(json.dumps({
        "api": {"key": "qa-demo-key", "base_url": args.mock, "model": "deepseek-flash"},
        "pet": {"size": 200, "x": 470, "y": 300, "always_on_top": True},
        "speech": {"bubble_seconds": 30, "typewriter": True},
    }, ensure_ascii=False), encoding="utf-8")
    cfg_official = (out / "shot-config-official.json").resolve()
    cfg_official.write_text(json.dumps({
        "api": {"key": "", "base_url": "https://api.deepseek.com", "model": "deepseek-flash"},
        "pet": {"size": 200, "x": 470, "y": 300, "always_on_top": True},
        "speech": {"bubble_seconds": 30, "typewriter": True},
    }, ensure_ascii=False), encoding="utf-8")

    root = tk.Tk()
    root.overrideredirect(True)
    root.geometry(f"+0+0")
    root.attributes("-topmost", True)
    w, h = root.winfo_screenwidth(), root.winfo_screenheight()
    photo = make_backdrop(root, w, h)
    root.update()
    user32.SetCursorPos(4, 4)
    time.sleep(0.5)
    report = {"screen": [w, h], "scenes": []}
    try:
        # 1) hero：宠物 + 聊天气泡 + 聊天窗同屏，全屏截图（mock API 保证有真实流式回复）
        report["scenes"].append(run_scene(
            base, cwd, ["--config", str(cfg), "--demo-chat", "你好呀"],
            out, "hero", wait=10.0, shots=2, interval=1.5, fullscreen=True))
        # 2) 设置窗口（官方 base_url，Key 为空——避免暴露 mock 地址）
        report["scenes"].append(run_scene(
            base, cwd, ["--config", str(cfg_official), "--open-settings"],
            out, "settings", wait=9.0, shots=1))
        # 3) 气泡特写（戳一戳式短句 / 上线问候）
        report["scenes"].append(run_scene(
            base, cwd, ["--config", str(cfg), "--demo-chat", "今天也要开心呀"],
            out, "bubble", wait=9.0, shots=1))
        # 4) 表情 showcase 连拍（只截宠物窗口，透明背景 + 渐变底）
        report["scenes"].append(run_scene(
            base, cwd, ["--config", str(cfg), "--showcase", "16"],
            out, "showcase", wait=4.0, shots=7, interval=1.8))
    finally:
        root.destroy()
    (out / "shots_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"screen": report["screen"], "shots": [s["file"] for sc in report["scenes"] for s in sc["shots"]]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
