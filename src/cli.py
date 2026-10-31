"""CLI 参数解析（SPEC §6）。

支持：``--version`` / ``--config PATH`` / ``--selftest`` / ``--showcase [SECONDS]`` /
``--debug`` / ``--dump-config``。
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass
class Options:
    version: bool = False
    config: str | None = None
    selftest: bool = False
    showcase: float | None = None
    debug: bool = False
    dump_config: bool = False
    open_settings: bool = False
    demo_chat: str | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="BlueWhalePet",
        description="蓝鲸桌宠 - DeepSeek 蓝色大肥鱼桌面宠物",
        epilog=(
            "示例: py src/main.py --selftest | "
            "py src/main.py --showcase 14 --config cfg.json | "
            "py src/main.py --dump-config"
        ),
    )
    parser.add_argument("--version", action="store_true", help="打印版本后退出")
    parser.add_argument("--config", metavar="PATH", default=None, help="使用指定配置文件（不存在则创建）")
    parser.add_argument("--selftest", action="store_true", help="自动自检（约 10 秒内退出）")
    parser.add_argument(
        "--showcase",
        nargs="?",
        const="",
        default=None,
        metavar="SECONDS",
        help="固定位置循环展示全部表情（默认 12 秒），到时自动退出",
    )
    parser.add_argument("--debug", action="store_true", help="日志输出到 stderr，DEBUG 级别")
    parser.add_argument("--dump-config", action="store_true", help="输出解析后的配置 JSON 到 stdout/数据目录")
    parser.add_argument(
        "--open-settings",
        action="store_true",
        help="正常启动后约 1.5s 自动打开设置窗口（约 8s 后自动关闭，供文档截图）",
    )
    parser.add_argument(
        "--demo-chat",
        metavar="TEXT",
        default=None,
        help="正常启动后自动打开聊天窗并发送 TEXT（供 QA mock API 验证流式/截图）",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> Options:
    parser = build_parser()
    namespace = parser.parse_args(argv)
    showcase_seconds: float | None = None
    if namespace.showcase is not None:
        raw = str(namespace.showcase).strip()
        if raw == "":
            showcase_seconds = 12.0
        else:
            try:
                showcase_seconds = float(raw)
            except ValueError:
                showcase_seconds = 12.0
        showcase_seconds = max(1.0, min(600.0, showcase_seconds))
    return Options(
        version=bool(namespace.version),
        config=namespace.config,
        selftest=bool(namespace.selftest),
        showcase=showcase_seconds,
        debug=bool(namespace.debug),
        dump_config=bool(namespace.dump_config),
        open_settings=bool(namespace.open_settings),
        demo_chat=(str(namespace.demo_chat) if namespace.demo_chat else None),
    )
