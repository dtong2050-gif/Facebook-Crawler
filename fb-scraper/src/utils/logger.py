"""Logger setup với rich console output và rotating file handler."""

import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler

_console = Console(stderr=True)

# Tránh tạo duplicate handlers khi module được import nhiều lần
_configured_loggers: set[str] = set()


def setup_logger(name: str, log_dir: Optional[Path] = None) -> logging.Logger:
    """Tạo và cấu hình logger với rich console handler và rotating file handler.

    Args:
        name: Tên module, thường là __name__
        log_dir: Thư mục lưu log file. Default: logs/ trong project root

    Returns:
        Logger đã được cấu hình
    """
    logger = logging.getLogger(name)

    if name in _configured_loggers:
        return logger

    _configured_loggers.add(name)
    logger.setLevel(logging.DEBUG)

    # Console handler dùng rich
    console_handler = RichHandler(
        console=_console,
        rich_tracebacks=True,
        markup=True,
        show_path=False,
        log_time_format="[%H:%M:%S]",
    )
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    # File handler với rotation
    if log_dir is None:
        log_dir = Path(__file__).parent.parent.parent / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"scraper_{datetime.now().strftime('%Y-%m-%d')}.log"

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(file_handler)

    return logger
