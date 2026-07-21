"""Application-wide logging configuration: a console handler and a
rotating file handler sharing one timestamp/level/module/message format.
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.config import get_settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "app.log"
MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3

_configured = False


def configure_logging() -> None:
    """Attaches a console handler and a rotating file handler to the root
    logger, using the level from `Settings.log_level`.

    Idempotent: subsequent calls in the same process are no-ops, so it is
    safe to call this from module import time (e.g. in src/api/main.py).
    """
    global _configured
    if _configured:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT)

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    _configured = True
