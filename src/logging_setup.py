"""日志初始化（SPEC §3）：数据目录 logs/app.log，1MB × 2 RotatingFileHandler。"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import constants as C

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOGGER_NAME = "bluewhale"


def setup_logging(debug: bool = False, log_file: Path | None = None) -> logging.Logger:
    """配置并返回应用 logger。失败时降级为 stderr / NullHandler，绝不抛异常。"""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        try:
            handler.close()
        except Exception:  # noqa: BLE001
            pass
        logger.removeHandler(handler)

    formatter = logging.Formatter(LOG_FORMAT)

    if log_file is not None:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(
                str(log_file),
                maxBytes=C.LOG_MAX_BYTES,
                backupCount=C.LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            fh.setLevel(logging.DEBUG if debug else logging.INFO)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except OSError:
            pass

    if debug or not logger.handlers:
        sh = logging.StreamHandler(stream=sys.stderr)
        sh.setLevel(logging.DEBUG if debug else logging.INFO)
        sh.setFormatter(formatter)
        logger.addHandler(sh)

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    if not name:
        return logging.getLogger(LOGGER_NAME)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
