"""蓝鲸桌宠入口（SPEC §6）。

用法：
  py src/main.py                 # 正常运行
  py src/main.py --version       # 蓝鲸桌宠 1.0.0
  py src/main.py --selftest      # 自动自检（约 10s）
  py src/main.py --showcase 14   # 固定位置展示全部表情（截图用）
  py src/main.py --config path   # 指定配置
  py src/main.py --dump-config   # 打印解析后的配置
  py src/main.py --debug         # stderr DEBUG 日志

本文件是打包入口，可被 ``python src/main.py`` 直接运行；所有同级模块使用绝对导入。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 确保以任意方式运行（脚本 / PyInstaller / Linux 引导壳 runpy）都能导入同级模块
_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

APP_VERSION = "1.0.0"
APP_NAME = "蓝鲸桌宠"


def _write_dump_config(payload: dict) -> None:
    try:
        import resources

        path = resources.dump_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    import cli

    try:
        options = cli.parse_args(argv)
    except SystemExit as exc:  # argparse 已打印用法
        return int(exc.code or 0)

    if options.version:
        print(f"{APP_NAME} {APP_VERSION}")
        return 0

    try:
        import platform_win

        platform_win.prepare_dpi()
    except Exception:  # noqa: BLE001
        pass

    import config as config_module
    import constants as C
    import logging_setup
    import resources
    import single_instance

    resources.ensure_dirs()
    logger = logging_setup.setup_logging(options.debug, resources.logs_dir() / "app.log")
    config_path, config_note = resources.resolve_config_path(options.config)
    if config_note:
        logger.warning(config_note)
    cfg, info = config_module.load_or_create_config(config_path)
    for warning in info.get("warnings", ()):
        logger.warning("配置提示: %s", warning)
    logger.info(
        "启动 %s %s | frozen=%s portable=%s | config=%s | data=%s | assets=%s",
        APP_NAME,
        APP_VERSION,
        resources.is_frozen(),
        resources.is_portable(),
        config_path,
        resources.data_dir(),
        resources.asset_root(),
    )
    logger.info("运行环境: python=%s platform=%s", sys.version.split()[0], sys.platform)

    if options.dump_config:
        payload = {
            "ok": True,
            "app": C.APP_NAME,
            "version": C.APP_VERSION,
            "config_path": str(config_path),
            "config_exists": config_path.is_file(),
            "data_dir": str(resources.data_dir()),
            "asset_root": str(resources.asset_root()),
            "frozen": resources.is_frozen(),
            "portable": resources.is_portable(),
            "dpi_scale": __import__("platform_win").dpi_scale(),
            "config": cfg,
        }
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        _write_dump_config(payload)
        return 0

    if options.selftest:
        import selftest

        return selftest.run_selftest(logger_=logger)

    if options.showcase is not None:
        import showcase

        return showcase.run_showcase(options.showcase, config_path, logger)

    # ---- 正常运行 ----
    instance = single_instance.SingleInstance(resources.data_dir(), logger)
    if not instance.acquire():
        logger.info("已有实例运行中，退出")
        return 0

    root = None
    app = None
    try:
        import tkinter as tk

        from app import PetApp

        root = tk.Tk(className=C.WM_CLASS)
        root.withdraw()
        root.title(C.APP_NAME)
        scale = 1.0
        try:
            scale = float(__import__("platform_win").apply_tk_scaling(root) or 1.0)
        except Exception:  # noqa: BLE001
            scale = 1.0
        app = PetApp(root, cfg, config_path, logger, scale=scale)
        app.start()
        if options.open_settings:
            try:
                root.after(1500, lambda: app.open_settings_autoclose(8000))
            except Exception:  # noqa: BLE001
                logger.debug("安排自动打开设置窗口失败", exc_info=True)
        if options.demo_chat:
            try:
                root.after(1200, lambda: app.demo_chat(str(options.demo_chat)))
            except Exception:  # noqa: BLE001
                logger.debug("安排 demo-chat 失败", exc_info=True)
        try:
            instance.start_wake_server(lambda: app._queue.put(("wake", None)))
        except Exception:  # noqa: BLE001
            logger.debug("启动二启唤醒监听失败", exc_info=True)
        root.mainloop()
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception("应用启动/运行失败")
        try:
            import platform_win

            platform_win.show_error_dialog(
                f"{APP_NAME} 启动失败",
                f"程序遇到错误：{exc}\n\n日志文件：\n{resources.logs_dir() / 'app.log'}",
            )
        except Exception:  # noqa: BLE001
            sys.stderr.write(f"{APP_NAME} 启动失败: {exc}\n")
        return 1
    finally:
        try:
            instance.release()
        except Exception:  # noqa: BLE001
            pass
        if app is not None:
            try:
                app.shutdown()
            except Exception:  # noqa: BLE001
                pass
        if root is not None:
            try:
                root.destroy()
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
