from __future__ import annotations
import ctypes, ctypes.wintypes as wt, json, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import winproc

user32 = ctypes.windll.user32
GWL_EXSTYLE=-20; GWL_STYLE=-16

@ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
def cb(hwnd, _):
    pid = wt.DWORD(); user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value in pids:
        r = wt.RECT(); user32.GetWindowRect(hwnd, ctypes.byref(r))
        t = ctypes.create_unicode_buffer(200); user32.GetWindowTextW(hwnd, t, 200)
        c = ctypes.create_unicode_buffer(200); user32.GetClassNameW(hwnd, c, 200)
        o = user32.GetWindow(hwnd, 4)  # GW_OWNER
        print(f"hwnd={hwnd} pid={pid.value} vis={bool(user32.IsWindowVisible(hwnd))} "
              f"rect=({r.left},{r.top},{r.right},{r.bottom}) cls={c.value!r} title={t.value!r} "
              f"owner={o} ex=0x{user32.GetWindowLongW(hwnd, GWL_EXSTYLE)&0xffffffff:08x} style=0x{user32.GetWindowLongW(hwnd, GWL_STYLE)&0xffffffff:08x}")
    return True

exe = Path(sys.argv[1]).resolve(); out = Path("qa/out/diag2"); out.mkdir(parents=True, exist_ok=True)
cfg = out/"c.json"; cfg.write_text(json.dumps({"pet":{"size":220,"x":320,"y":300}}, ensure_ascii=False), encoding="utf-8")
winproc.kill_by_name(exe.stem); time.sleep(0.5)
p = subprocess.Popen([str(exe), "--config", str(cfg)], cwd=str(out))
try:
    time.sleep(8)
    pids = winproc.family(p.pid); print("pids:", sorted(pids))
    user32.EnumWindows(cb, 0)
    pt = wt.POINT(537, 512); h = user32.WindowFromPoint(pt)
    print("hit:", h, "real child?", user32.ChildWindowFromPointEx(h, pt, 1) if h else None)
finally:
    p.terminate()
    try: p.wait(timeout=5)
    except Exception: winproc.kill_tree(p.pid)
    winproc.kill_by_name(exe.stem)
