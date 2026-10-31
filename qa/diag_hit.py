"""诊断：便携 exe 的宠物窗口是否可点击（z 序/命中测试/扩展样式）。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import winproc  # noqa: E402

user32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_LAYERED = 0x00080000


class POINT(ctypes.Structure):
    _fields_ = [("x", wt.LONG), ("y", wt.LONG)]


def hit(x: int, y: int) -> int:
    pt = POINT(x, y)
    return int(user32.WindowFromPoint(pt))


def main() -> int:
    exe = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path("qa/out/diag")
    out.mkdir(parents=True, exist_ok=True)
    cfg = out / "diag-config.json"
    cfg.write_text(json.dumps({
        "api": {"key": "qa", "base_url": "http://127.0.0.1:8765", "model": "deepseek-flash"},
        "pet": {"size": 220, "x": 320, "y": 300, "always_on_top": True},
        "speech": {"bubble_seconds": 30},
    }, ensure_ascii=False), encoding="utf-8")
    winproc.kill_by_name(exe.stem)
    time.sleep(0.5)
    p = subprocess.Popen([str(exe), "--config", str(cfg)], cwd=str(out))
    try:
        wins = winproc.wait_windows(p.pid, timeout=40)
        print("family:", sorted(winproc.family(p.pid)))
        for w in wins:
            hwnd = w["hwnd"]
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            print(f"win {w['title']!r} hwnd={hwnd} rect={w['rect']} "
                  f"topmost={bool(ex & WS_EX_TOPMOST)} transparent={bool(ex & WS_EX_TRANSPARENT)} "
                  f"layered={bool(ex & WS_EX_LAYERED)}")
        pet = max(wins, key=lambda w: (w["rect"][2] - w["rect"][0]) * (w["rect"][3] - w["rect"][1]))
        l, t, r, b = pet["rect"]
        cx, cy = (l + r) // 2, (t + b) // 2
        print("center:", cx, cy, "hit:", hit(cx, cy), "pet hwnd:", pet["hwnd"], "same:", hit(cx, cy) == pet["hwnd"])
        # 列出屏幕该点最上层窗口的标题
        h = hit(cx, cy)
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, buf, 256)
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        print("top window at center:", buf.value, "pid:", pid.value)
        return 0
    finally:
        p.terminate()
        try:
            p.wait(timeout=5)
        except Exception:  # noqa: BLE001
            winproc.kill_tree(p.pid)
        winproc.kill_by_name(exe.stem)


if __name__ == "__main__":
    sys.exit(main())
