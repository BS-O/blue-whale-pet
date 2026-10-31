from __future__ import annotations
import json, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import winproc
import interact_win as IW

arg = sys.argv[1]
if arg == "dev":
    ROOT = Path(__file__).resolve().parent.parent
    cmd = [sys.executable, str(ROOT / "src" / "main.py")]
    exe = Path(sys.executable)
    stem = "python"
else:
    exe = Path(arg).resolve(); cmd = [str(exe)]
    stem = exe.stem
out = Path("qa/out/diag5").resolve(); out.mkdir(parents=True, exist_ok=True)
cfg = out/"c.json"
cfg.write_text(json.dumps({"api":{"key":"qa","base_url":"http://127.0.0.1:8765","model":"deepseek-flash"},
 "pet":{"size":220,"x":320,"y":300},"speech":{"bubble_seconds":30},
 "behavior":{"greet_on_start":False},"system":{"tray":True}}, ensure_ascii=False), encoding="utf-8")
for _ in range(3):
    if not winproc.kill_by_name(stem): break
    time.sleep(0.5)
p = subprocess.Popen(cmd + ["--config", str(cfg)], cwd=str(out))
def titles():
    return [w["title"] for w in winproc.find_windows(winproc.family(p.pid))]
try:
    wins = winproc.wait_windows(p.pid, timeout=40)
    pet = [w for w in wins if "蓝鲸" in w["title"] and "气泡" not in w["title"]][0]
    l,t,r,b = pet["rect"]; cx, cy = (l+r)//2, (t+b)//2
    print("pet:", pet["rect"], "before:", titles())
    IW.mouse(IW.MOUSEEVENTF["MOVE"], x=cx, y=cy); time.sleep(0.3)
    IW.click("left"); time.sleep(1.2)
    print("after single click:", titles())
    IW.mouse(IW.MOUSEEVENTF["MOVE"], x=cx, y=cy); time.sleep(0.2)
    IW.click("left"); time.sleep(0.08); IW.click("left"); time.sleep(1.2)
    print("after double click:", titles())
finally:
    p.terminate()
    try: p.wait(timeout=5)
    except Exception: winproc.kill_tree(p.pid)
    for _ in range(3):
        if not winproc.kill_by_name(stem): break
        time.sleep(0.5)
