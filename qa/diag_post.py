from __future__ import annotations
import ctypes, ctypes.wintypes as wt, json, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import winproc

user32 = ctypes.windll.user32
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_MOUSEMOVE, WM_MOUSEWHEEL = 0x0200, 0x020A

def lp(x, y): return (y << 16) | (x & 0xFFFF)

exe = Path(sys.argv[1]).resolve(); out = Path("qa/out/diag3"); out.mkdir(parents=True, exist_ok=True)
cfg = out/"c.json"; cfg.write_text(json.dumps({"pet":{"size":220,"x":320,"y":300},"speech":{"bubble_seconds":30}}, ensure_ascii=False), encoding="utf-8")
winproc.kill_by_name(exe.stem); time.sleep(0.5)
p = subprocess.Popen([str(exe), "--config", str(cfg)], cwd=str(out))
try:
    wins = winproc.wait_windows(p.pid, timeout=40)
    pet = [w for w in wins if "蓝鲸" in w["title"] and "气泡" not in w["title"]][0]
    hwnd = pet["hwnd"]; l,t,r,b = pet["rect"]
    print("pet:", hwnd, pet["rect"], "pids:", sorted(winproc.family(p.pid)))
    user32.SetForegroundWindow(hwnd); user32.BringWindowToTop(hwnd); time.sleep(0.5)
    cx, cy = (r-l)//2, (b-t)//2
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lp(cx, cy)); time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp(cx, cy)); time.sleep(1.5)
    titles = [w["title"] for w in winproc.find_windows(winproc.family(p.pid))]
    print("after click windows:", titles)
    # 右键按下+移动 → 拖拽
    user32.PostMessageW(hwnd, WM_RBUTTONDOWN, 2, lp(cx, cy)); time.sleep(0.2)
    for i in range(1, 11):
        user32.PostMessageW(hwnd, WM_MOUSEMOVE, 2, lp(cx + 16*i, cy - 6*i)); time.sleep(0.03)
    user32.PostMessageW(hwnd, WM_RBUTTONUP, 0, lp(cx + 160, cy - 60)); time.sleep(1.2)
    print("config after drag:", json.loads(cfg.read_text(encoding='utf-8')).get("pet"))
    # 滚轮
    for _ in range(3):
        user32.PostMessageW(hwnd, WM_MOUSEWHEEL, (120 << 16), lp(cx, cy)); time.sleep(0.15)
    time.sleep(0.8)
    print("config after wheel:", json.loads(cfg.read_text(encoding='utf-8')).get("pet"))
    log = Path(cfg).parent.parent.parent.parent  # unused
    print("log tail:")
    for base in [Path(str(cfg)).parents[0], Path.home()/"AppData/Roaming/BlueWhalePet"]:
        pass
finally:
    p.terminate()
    try: p.wait(timeout=5)
    except Exception: winproc.kill_tree(p.pid)
    winproc.kill_by_name(exe.stem)
