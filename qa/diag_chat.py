from __future__ import annotations
import ctypes, ctypes.wintypes as wt, json, subprocess, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import winproc

user32 = ctypes.windll.user32
MOUSEEVENTF = {"MOVE": 0x0001, "LEFTDOWN": 0x0002, "LEFTUP": 0x0004}

import interact_win as IW
mouse = IW.mouse
MOUSEEVENTF = IW.MOUSEEVENTF
def click():
    IW.mouse(IW.MOUSEEVENTF["LEFTDOWN"]); time.sleep(0.03)
    IW.mouse(IW.MOUSEEVENTF["LEFTUP"])

exe = Path(sys.argv[1]).resolve(); out = Path("qa/out/diag4").resolve(); out.mkdir(parents=True, exist_ok=True)
cfg = out/"c.json"; cfg.write_text(json.dumps({"api":{"key":"qa","base_url":"http://127.0.0.1:8765","model":"deepseek-flash"},"pet":{"size":220,"x":320,"y":300},"speech":{"bubble_seconds":30}}, ensure_ascii=False), encoding="utf-8")
winproc.kill_by_name(exe.stem); time.sleep(0.8)
p = subprocess.Popen([str(exe), "--config", str(cfg)], cwd=str(out))
try:
    wins = winproc.wait_windows(p.pid, timeout=40)
    pet = [w for w in wins if "蓝鲸" in w["title"] and "气泡" not in w["title"]][0]
    l,t,r,b = pet["rect"]; cx, cy = (l+r)//2, (t+b)//2
    print("pet rect:", pet["rect"])
    mouse(MOUSEEVENTF["MOVE"], cx, cy); time.sleep(0.3)
    click(); time.sleep(0.06); click(); time.sleep(1.0)
    titles = [w["title"] for w in winproc.find_windows(winproc.family(p.pid))]
    print("after double click:", titles)
    # 若聊天窗出现，输入文字并回车
    if any("聊天" in x for x in titles):
        chat = [w for w in winproc.find_windows(winproc.family(p.pid)) if "聊天" in w["title"]][0]
        user32.SetForegroundWindow(chat["hwnd"]); time.sleep(0.5)
        for ch in "你好呀":
            user32.PostMessageW(chat["hwnd"], 0x0102, ord(ch), 0)  # WM_CHAR
            time.sleep(0.02)
        user32.PostMessageW(chat["hwnd"], 0x0100, 0x0D, 0)  # WM_KEYDOWN Enter
        user32.PostMessageW(chat["hwnd"], 0x0101, 0x0D, 0)
        time.sleep(3)
        print("stats:", json.loads(urllib.request.urlopen("http://127.0.0.1:8765/_stats", timeout=3).read()))
finally:
    p.terminate()
    try: p.wait(timeout=5)
    except Exception: winproc.kill_tree(p.pid)
    for _ in range(3):
        if not winproc.kill_by_name(exe.stem): break
        time.sleep(0.5)
