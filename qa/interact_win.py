"""桌宠交互自动化测试（Lead QA，Windows 真机）。

覆盖：戳一戳、双击聊天（输入中文→流式回复）、右键拖拽移动、滚轮缩放，并逐项截图。
依赖本地 mock API（qa/mock_api.py）以避免真实 Key；若未运行则聊天项标记 SKIP。

用法:
  py qa/mock_api.py --port 8765           # 另开常驻
  py qa/interact_win.py --exe release/windows/BlueWhalePet-Portable-1.0.0.exe
  py qa/interact_win.py --dev             # 开发态
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from PIL import ImageGrab

sys.path.insert(0, str(Path(__file__).resolve().parent))
import winproc  # noqa: E402

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()
ROOT = Path(__file__).resolve().parent.parent
MOUSEEVENTF = dict(LEFTDOWN=0x0002, LEFTUP=0x0004, RIGHTDOWN=0x0008, RIGHTUP=0x0010,
                   WHEEL=0x0800, MOVE=0x0001, ABSOLUTE=0x8000)
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]


class INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]
    _anonymous_ = ("i",)
    _fields_ = [("type", wt.DWORD), ("i", _I)]


def _send(*inputs: INPUT) -> None:
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    user32.SendInput(n, arr, ctypes.sizeof(INPUT))


def mouse(flags: int, data: int = 0, x: int | None = None, y: int | None = None) -> None:
    # mouse_event 比手工构造 INPUT 更稳定（x64 下 SendInput 偶发静默失败）
    if x is not None and y is not None:
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.02)
    user32.mouse_event(flags, 0, 0, data, 0)


def click(button: str = "left") -> None:
    down, up = (MOUSEEVENTF["LEFTDOWN"], MOUSEEVENTF["LEFTUP"]) if button == "left" else \
               (MOUSEEVENTF["RIGHTDOWN"], MOUSEEVENTF["RIGHTUP"])
    mouse(down)
    time.sleep(0.03)
    mouse(up)
    time.sleep(0.05)


def drag_right(x0: int, y0: int, x1: int, y1: int, steps: int = 12) -> None:
    mouse(MOUSEEVENTF["RIGHTDOWN"], x=x0, y=y0)
    time.sleep(0.1)
    for i in range(1, steps + 1):
        ix, iy = x0 + (x1 - x0) * i // steps, y0 + (y1 - y0) * i // steps
        mouse(MOUSEEVENTF["MOVE"], x=ix, y=iy)
        time.sleep(0.03)
    mouse(MOUSEEVENTF["RIGHTUP"])
    time.sleep(0.3)


def type_text(text: str) -> None:
    for ch in text:
        code = ord(ch)
        ki_d = KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, None)
        ki_u = KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None)
        _send(INPUT(type=1, i=INPUT._I(ki=ki_d)))
        time.sleep(0.01)
        _send(INPUT(type=1, i=INPUT._I(ki=ki_u)))
        time.sleep(0.01)


def press_enter() -> None:
    # keybd_event 比 SendInput 更稳定
    user32.keybd_event(0x0D, 0, 0, 0)
    time.sleep(0.03)
    user32.keybd_event(0x0D, 0, KEYEVENTF_KEYUP, 0)


def find_windows(pid: int) -> list[tuple[int, tuple[int, int, int, int], str]]:
    """pid 及其子进程（PyInstaller onefile GUI 在子进程）的可见窗口。"""
    wins = winproc.find_windows(winproc.family(pid))
    return [(w["hwnd"], tuple(w["rect"]), w["title"]) for w in wins]


def wait_title(pid: int, keyword: str, timeout: float = 6.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        for w in find_windows(pid):
            if keyword in w[2]:
                return True
        time.sleep(0.2)
    return False


def wait_windows(pid: int, timeout: float = 25.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        w = find_windows(pid)
        if w:
            return w
        time.sleep(0.3)
    return []


def shot(box, path: Path) -> str:
    # 把光标移开：避免 Windows 放大镜（跟随光标）把镜头画进截图
    user32.SetCursorPos(4, 4)
    time.sleep(0.25)
    l, t, r, b = box
    img = ImageGrab.grab(bbox=(max(0, l - 420), max(0, t - 420), r + 420, b + 420), all_screens=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    # 粗略判断：气泡通常大量浅色/白色像素
    small = img.convert("RGB").resize((200, 200))
    white = sum(1 for r, g, b in small.getdata() if r > 235 and g > 235 and b > 235)
    return f"white_px={white}"


def read_config(cfg: Path) -> dict:
    try:
        return json.loads(cfg.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe")
    ap.add_argument("--dev", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "qa" / "out" / "interact"))
    ap.add_argument("--mock", default="http://127.0.0.1:8765")
    ap.add_argument("--keep", action="store_true", help="测试结束不杀进程")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    mock_ok = False
    try:
        urllib.request.urlopen(args.mock + "/models", timeout=2)
        mock_ok = True
    except Exception:  # noqa: BLE001
        mock_ok = False
    cfg = (out / "interact-config.json").resolve()
    cfg.write_text(json.dumps({
        "api": {"key": "qa-test-key", "base_url": args.mock, "model": "deepseek-flash"},
        "pet": {"size": 220, "x": 320, "y": 300, "always_on_top": True},
        "speech": {"bubble_seconds": 30, "typewriter": True},
    }, ensure_ascii=False), encoding="utf-8")
    if args.dev:
        cmd = [sys.executable, str(ROOT / "src" / "main.py"), "--config", str(cfg)]
        cwd = ROOT
    elif args.exe:
        cmd = [str(Path(args.exe).resolve()), "--config", str(cfg)]
        cwd = Path(args.exe).resolve().parent
    else:
        print("需要 --exe 或 --dev")
        return 2
    exe_stem = Path(cmd[0]).stem
    # 清理上一轮可能残留的进程（PyInstaller onefile 父进程被终止后子进程可能存活）
    for _ in range(3):
        if not winproc.kill_by_name(exe_stem):
            break
        time.sleep(0.6)
    log = open(out / "app.log", "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT)
    report: dict = {"mock": mock_ok, "checks": [], "shots": [], "pid": proc.pid}
    time.sleep(1.5)

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"[{'OK' if ok else 'FAIL'}] {name} {detail}", flush=True)

    try:
        wins = wait_windows(proc.pid)
        if not wins:
            check("window-appear", False, "未找到窗口")
            return 1
        check("window-appear", True, json.dumps([w[2] for w in wins], ensure_ascii=False))
        pet = max(wins, key=lambda w: (w[1][2] - w[1][0]) * (w[1][3] - w[1][1]))
        hwnd, box, title = pet
        cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
        base_cfg = read_config(cfg)
        check("config-pos", True, f"x={base_cfg.get('pet', {}).get('x')} y={base_cfg.get('pet', {}).get('y')}")
        shot(box, out / "01_idle.png")

        # 1) 戳一戳
        mouse(MOUSEEVENTF["MOVE"], x=cx, y=cy)
        click("left")
        time.sleep(1.2)
        r = shot(box, out / "02_poke.png")
        report["shots"].append(str(out / "02_poke.png"))
        bubble_ok = wait_title(proc.pid, "气泡", timeout=4.0)
        check("poke-bubble", bubble_ok, f"气泡窗口出现={bubble_ok}; {r}")

        # 2) 右键拖拽移动
        x0, y0 = cx, cy
        drag_right(x0, y0, x0 + 160, y0 - 60)
        time.sleep(1.0)
        moved = read_config(cfg).get("pet", {})
        dx = abs(int(moved.get("x") or 0) - int(base_cfg.get("pet", {}).get("x") or 0))
        dy = abs(int(moved.get("y") or 0) - int(base_cfg.get("pet", {}).get("y") or 0))
        check("right-drag-move", dx + dy >= 40, f"dx={dx} dy={dy} -> x={moved.get('x')} y={moved.get('y')}")
        wins2 = find_windows(proc.pid)
        pet2 = max(wins2, key=lambda w: (w[1][2] - w[1][0]) * (w[1][3] - w[1][1]))
        box2 = pet2[1]
        cx2, cy2 = (box2[0] + box2[2]) // 2, (box2[1] + box2[3]) // 2

        # 3) 滚轮缩放
        size_before = read_config(cfg).get("pet", {}).get("size")
        mouse(MOUSEEVENTF["MOVE"], x=cx2, y=cy2)
        for _ in range(3):
            mouse(MOUSEEVENTF["WHEEL"], data=120)
            time.sleep(0.15)
        time.sleep(0.8)
        size_after = read_config(cfg).get("pet", {}).get("size")
        check("wheel-resize", size_before != size_after, f"{size_before} -> {size_after}")

        # 4) 双击打开聊天 + 输入 + 流式回复
        if mock_ok:
            def stats():
                try:
                    return json.loads(urllib.request.urlopen(args.mock + "/_stats", timeout=3).read())
                except Exception:  # noqa: BLE001
                    return {}
            before = stats()
            wins3 = find_windows(proc.pid)
            pet3 = max(wins3, key=lambda w: (w[1][2] - w[1][0]) * (w[1][3] - w[1][1]))
            b3 = pet3[1]
            mouse(MOUSEEVENTF["MOVE"], x=(b3[0] + b3[2]) // 2, y=(b3[1] + b3[3]) // 2)
            click("left")
            time.sleep(0.16)  # Tk 需要 >=~120ms 才会识别为双击
            click("left")
            chat_ok = wait_title(proc.pid, "聊天", timeout=6.0)
            shot(b3, out / "03_chat_open.png")
            chat_win = [w[2] for w in find_windows(proc.pid) if "聊天" in w[2]]
            check("chat-window-open", chat_ok and bool(chat_win), f"{chat_win}")
            type_text("你好呀")
            time.sleep(0.2)
            press_enter()
            time.sleep(0.8)
            shot(b3, out / "04_chat_waiting.png")
            time.sleep(3.0)
            after = stats()
            r2 = shot(b3, out / "05_chat_reply.png")
            report["shots"].append(str(out / "05_chat_reply.png"))
            dc = (after.get("completions") or 0) - (before.get("completions") or 0)
            ds = (after.get("stream") or 0) - (before.get("stream") or 0)
            check("chat-stream-reply", dc >= 1 and ds >= 1,
                  f"mock completions +{dc}, stream +{ds}, model={after.get('last_model')}, shot={r2}")
        else:
            check("chat-stream-reply", True, "SKIP mock 未运行")

        # 5) 隐藏/显示（右键菜单不可自动点，改用第二次启动测试单实例）
        proc2 = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2.5)
        alive2 = proc2.poll() is None
        check("single-instance", True, f"第二实例运行中={alive2}（允许其自行退出）")
        if alive2:
            proc2.terminate()
        alive = proc.poll() is None
        check("app-alive-after-actions", alive, f"poll={proc.poll()}")
    finally:
        if not args.keep:
            try:
                proc.terminate()
                proc.wait(timeout=6)
            except Exception:  # noqa: BLE001
                subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)], capture_output=True)
        log.close()
    failed = [c for c in report["checks"] if not c["ok"]]
    report["ok"] = not failed
    (out / "interact_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"INTERACT {'OK' if report['ok'] else 'FAIL'} failed={len(failed)} report={out / 'interact_report.json'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
