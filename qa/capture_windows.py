"""通用窗口截图工具（Lead QA/文档）。

启动命令（可带任意额外参数，如 --demo-chat / --open-settings），等待窗口出现，
对每个可见窗口按窗口矩形截图，并输出窗口标题/矩形 JSON。

用法:
  py qa/capture_windows.py --dev --extra "--config qa/out/t.json --demo-chat 你好呀" --out docs/screenshots
  py qa/capture_windows.py --exe release/windows/BlueWhalePet-Portable-1.0.0.exe --extra "--showcase 10" --out qa/out/shot
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

from PIL import ImageGrab

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()
ROOT = Path(__file__).resolve().parent.parent


def find_windows(pid: int):
    out = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if r.right - r.left > 20 and r.bottom - r.top > 20:
                out.append({"hwnd": hwnd, "rect": [r.left, r.top, r.right, r.bottom], "title": buf.value})
        return True

    user32.EnumWindows(cb, 0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe")
    ap.add_argument("--dev", action="store_true")
    ap.add_argument("--extra", default="", help="额外命令行参数（字符串）")
    ap.add_argument("--out", default=str(ROOT / "qa" / "out" / "capture"))
    ap.add_argument("--wait", type=float, default=2.5)
    ap.add_argument("--shots", type=int, default=1)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--pad", type=int, default=8)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    extra = args.extra.split() if args.extra else []
    if args.dev:
        cmd = [sys.executable, str(ROOT / "src" / "main.py")] + extra
        cwd = ROOT
    else:
        cmd = [str(Path(args.exe).resolve())] + extra
        cwd = Path(args.exe).resolve().parent
    proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    report = {"cmd": cmd, "shots": []}
    try:
        time.sleep(args.wait)
        for i in range(args.shots):
            wins = find_windows(proc.pid)
            user32.SetCursorPos(4, 4)  # 避开 Windows 放大镜镜头
            time.sleep(0.25)
            for w in wins:
                l, t, r, b = w["rect"]
                box = (max(0, l - args.pad), max(0, t - args.pad), r + args.pad, b + args.pad)
                name = f"shot_{i:02d}_w{w['hwnd']}.png"
                ImageGrab.grab(bbox=box, all_screens=True).save(out / name)
                report["shots"].append({"file": str(out / name), "title": w["title"], "rect": w["rect"]})
            time.sleep(args.interval)
        report["windows"] = find_windows(proc.pid)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=6)
        except Exception:  # noqa: BLE001
            subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)], capture_output=True)
        if proc.stdout:
            log = proc.stdout.read()
            (out / "app.log").write_text(log, encoding="utf-8")
    (out / "capture_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
