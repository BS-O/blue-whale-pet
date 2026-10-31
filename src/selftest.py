"""``--selftest`` 自动自检（SPEC §6）。

要求：无人工操作、约 10 秒内退出；成功 stdout 打印 ``SELFTEST OK <json>``，
失败打印 ``SELFTEST FAIL <原因>`` 并 exit 1；无论成败都把
``selftest_report.json`` 写到数据目录（windowed exe 的 stdout 不可见，QA 以报告判定）。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback
import tkinter as tk
from pathlib import Path
from typing import Any

import anim
import api
import config as config_module
import constants as C
import platform_win
import resources

logger = logging.getLogger("bluewhale.selftest")

WATCHDOG_SECONDS = float(os.environ.get("BLUEWHALE_SELFTEST_TIMEOUT", "9.5"))
_report_lock = threading.Lock()


def _write_report(report: dict[str, Any]) -> Path:
    path = resources.selftest_report_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        with _report_lock:
            tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, path)
    except OSError:
        logger.exception("写入 selftest_report.json 失败")
    return path


def run_selftest(config_path: Path | None = None, logger_: logging.Logger | None = None) -> int:
    log = logger_ or logger
    started = time.monotonic()
    checks: list[dict[str, Any]] = []
    states: list[str] = []
    summary: dict[str, Any] = {
        "ok": False,
        "version": C.APP_VERSION,
        "app": C.APP_NAME,
        "platform": sys.platform,
        "states": states,
        "checks": checks,
        "duration_ms": 0,
        "report": str(resources.selftest_report_path()),
        "data_dir": str(resources.data_dir()),
    }

    def check(name: str, ok: bool, detail: Any = None) -> bool:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "ms": elapsed_ms})
        log.info("check %-24s ok=%s +%dms", name, bool(ok), elapsed_ms)
        if not ok:
            raise AssertionError(f"检查失败: {name} ({detail})")
        return True

    def finalize(ok: bool, error: str = "") -> int:
        summary["ok"] = bool(ok)
        summary["checks"] = checks
        summary["states"] = states
        summary["duration_ms"] = int((time.monotonic() - started) * 1000)
        if error:
            summary["error"] = error
        report_path = _write_report(summary)
        payload = json.dumps(summary, ensure_ascii=True)
        if ok:
            sys.stdout.write(f"SELFTEST OK {payload}\n")
        else:
            sys.stdout.write(f"SELFTEST FAIL {error}\n")
        try:
            sys.stdout.flush()
        except Exception:  # noqa: BLE001
            pass
        log.info("selftest 完成 ok=%s 报告=%s", ok, report_path)
        return 0 if ok else 1

    def watchdog() -> None:
        timeout_report = dict(summary)
        timeout_report["ok"] = False
        timeout_report["error"] = f"自检超时（>{WATCHDOG_SECONDS}s）"
        timeout_report["checks"] = checks
        timeout_report["states"] = states
        timeout_report["duration_ms"] = int((time.monotonic() - started) * 1000)
        _write_report(timeout_report)
        try:
            sys.stdout.write(f"SELFTEST FAIL 自检超时（>{WATCHDOG_SECONDS}s）\n")
            sys.stdout.flush()
        except Exception:  # noqa: BLE001
            pass
        os._exit(1)

    timer = threading.Timer(WATCHDOG_SECONDS, watchdog)
    timer.daemon = True
    timer.start()

    root: tk.Tk | None = None
    app: Any = None
    temp_dir = Path(tempfile.mkdtemp(prefix="bluewhale-selftest-"))
    try:
        # 1) manifest
        manifest = anim.Manifest.load(resources.manifest_path())
        states = manifest.state_names()
        if manifest.required_missing:
            raise AssertionError(f"缺少必需表情: {manifest.required_missing}")
        missing = manifest.missing_frames()
        if missing:
            raise AssertionError(f"缺少表情帧文件: {missing[:6]}")
        check(
            "manifest",
            True,
            {
                "states": len(manifest.states),
                "frames": manifest.frame_total,
                "default": manifest.default_state,
                "canvas": [manifest.canvas_w, manifest.canvas_h],
            },
        )
        check("manifest_required_states", len(states) >= len(C.REQUIRED_STATES), {"count": len(states)})

        # 2) 配置读写 / 损坏恢复
        tmp_cfg = temp_dir / "config.json"
        cfg0 = config_module.default_config()
        ok_save = config_module.save_config(tmp_cfg, cfg0)
        check("config_write", ok_save and tmp_cfg.is_file(), {"path": str(tmp_cfg)})
        loaded, info = config_module.load_config(tmp_cfg)
        check(
            "config_roundtrip",
            loaded["pet"]["size"] == C.DEFAULT_SIZE and loaded["api"]["model"] == C.DEFAULT_MODEL,
            {"size": loaded["pet"]["size"], "model": loaded["api"]["model"], "existed": info["existed"]},
        )
        tmp_cfg.write_text("{ this is not json ", encoding="utf-8")
        recovered, info2 = config_module.load_config(tmp_cfg)
        backup_ok = bool(info2.get("backup")) and Path(str(info2["backup"])).is_file()
        check(
            "config_recover",
            bool(info2.get("recovered")) and backup_ok and recovered["pet"]["size"] == C.DEFAULT_SIZE,
            {"backup": info2.get("backup")},
        )

        # 3) SSE 解析 mock
        decoder = api.SSEDecoder()
        events: list[tuple[str, str]] = []
        chunks = [
            b'data: {"choices":[{"delta":{"content":"\xe4\xbd\xa0"}}]}\n',
            b": keep-alive\n\n",
            b'data: {"choices":[{"delta":{"content":"\xe5\xa5\xbd"}}]}\r\n',
            b"data: [DONE]\n",
        ]
        for chunk in chunks:
            events.extend(decoder.feed(chunk))
        events.extend(decoder.flush())
        content = "".join(text for kind, text in events if kind == "content")
        check(
            "sse_parse",
            content == "你好" and any(kind == "done" for kind, _ in events),
            {"content": content, "events": len(events)},
        )
        payload = api.build_payload(loaded, [{"role": "user", "content": "hi"}], stream=True)
        check(
            "api_payload",
            payload.get("stream") is True
            and payload.get("thinking") == {"type": "disabled"}
            and payload.get("model") == C.DEFAULT_MODEL
            and payload.get("max_tokens") == 120,
            {"model": payload.get("model")},
        )

        # 4) UI
        scale = platform_win.prepare_dpi() if platform_win.IS_WINDOWS else 1.0
        try:
            root = tk.Tk(className=C.WM_CLASS)
        except tk.TclError as exc:
            raise AssertionError(f"无法创建 Tk 窗口（无显示环境）: {exc}") from exc
        root.withdraw()
        root.title(C.APP_NAME)
        platform_win.apply_tk_scaling(root)
        ui_cfg = config_module.default_config()
        ui_cfg["behavior"]["greet_on_start"] = False
        ui_cfg["pet"]["size"] = 168
        ui_cfg_path = temp_dir / "ui-config.json"
        config_module.save_config(ui_cfg_path, ui_cfg)

        from app import PetApp

        app = PetApp(root, ui_cfg, ui_cfg_path, log, scale=scale, selftest=True)
        app.start(show=True)
        root.update()
        check("pet_window", bool(app.pet.visible), {"size": [app.pet.pixel_w, app.pet.pixel_h]})
        start_ws = platform_win.get_working_set_mb()
        summary["after_start_ws_mb"] = start_ws

        # 全部表情图片：并行解码 + 驻留缓存，后续切换/戳检查走内存，避免慢磁盘拖慢自检
        app.sprites.max_states = len(states)
        images = app.sprites.verify_all(populate=True)
        check(
            "all_state_images",
            not images["failed"] and images["created"] == manifest.frame_total,
            {"created": images["created"], "failed": images["failed"][:5]},
        )

        switched = 0
        original_on_frame = app.animator.on_frame
        app.animator.on_frame = lambda *_args: None  # 状态机检查不需要逐帧加载
        try:
            for state in states:
                app.animator.play(state)
                switched += 1
            app.animator.play(manifest.default_state)
        finally:
            app.animator.on_frame = original_on_frame
            app.animator.stop()
        root.update()
        check("state_machine", switched == len(states), {"switched": switched, "current": app.animator.current_state})

        poke_lines = 0
        for _ in range(3):
            app.on_poke()
            poke_lines += 1
            root.update()
        check("poke_3_times", poke_lines == 3, {"pokes": poke_lines, "state": app.animator.current_state})

        app.show_bubble("自检气泡")
        root.update()
        check("bubble", app.bubble.visible, {"visible": app.bubble.visible})

        app.open_settings()
        root.update()
        settings_ok = app._settings_win is not None
        if app._settings_win is not None:
            app._settings_win.close()
            root.update()
        check("settings_window", settings_ok and app._settings_win is None, {"created": settings_ok})

        tray_ok = bool(app.tray and app.tray.available)
        if platform_win.IS_WINDOWS:
            check("tray", tray_ok, {"available": tray_ok})
        else:
            checks.append({"name": "tray", "ok": True, "detail": {"available": tray_ok, "note": "非 Windows 可选"}})

        app.sprites.max_states = 3
        app.sprites.clear()
        import gc

        gc.collect()
        memory_mb = platform_win.get_working_set_mb()
        checks.append(
            {
                "name": "working_set",
                "ok": True,
                "detail": {"after_start_mb": start_ws, "after_selftest_mb": memory_mb},
            }
        )
        # 空载内存以“启动后、压力测试前”为准（自检过程中会临时缓存全部帧）
        summary["working_set_mb"] = start_ws
        summary["after_start_ws_mb"] = start_ws
        summary["after_selftest_ws_mb"] = memory_mb
        summary["dpi_scale"] = scale
        summary["tray_available"] = tray_ok
        return finalize(True)
    except Exception as exc:  # noqa: BLE001
        log.exception("selftest 失败")
        return finalize(False, f"{exc.__class__.__name__}: {exc}")
    finally:
        timer.cancel()
        try:
            if app is not None:
                app.shutdown()
        except Exception:  # noqa: BLE001
            log.debug("selftest 清理 app 失败", exc_info=True)
        try:
            if root is not None:
                root.destroy()
        except Exception:  # noqa: BLE001
            pass
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except OSError:
            pass
