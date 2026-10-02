"""Structured logging configuration for AstraRun."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_LOGGING_INITIALIZED = False


class SecretScrubbingFilter(logging.Filter):
    """Filter that sanitizes credentials, tokens, and secrets from all log messages."""
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from astrarun.security.secret_broker import SecretBroker
            broker = SecretBroker.get_instance()
            if isinstance(record.msg, str):
                record.msg = broker.scrub_text(record.msg)[0]
            if record.args:
                scrubbed_args = []
                for arg in record.args:
                    if isinstance(arg, str):
                        scrubbed_args.append(broker.scrub_text(arg)[0])
                    else:
                        scrubbed_args.append(arg)
                record.args = tuple(scrubbed_args)
        except Exception:
            pass
        return True


def setup_logging(
    log_file: Optional[str | Path] = None,
    level: str = "INFO",
    max_bytes: int = 10_485_760,
    backup_count: int = 3,
) -> logging.Logger:
    """Initialize structured rotating file and console logging."""
    global _LOGGING_INITIALIZED
    logger = logging.getLogger("astrarun")

    if _LOGGING_INITIALIZED:
        return logger

    from astrarun.core.paths import get_logs_dir, is_release_mode

    if log_file is None:
        if is_release_mode():
            log_path = get_logs_dir() / "astrarun.log"
        else:
            log_path = Path("logs/astrarun.log")
    else:
        log_path = Path(log_file)

    log_path.parent.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    scrubber = SecretScrubbingFilter()
    logger.addFilter(scrubber)

    # Rotating file handler
    file_handler = RotatingFileHandler(
        filename=str(log_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler (only attach if stdout exists, e.g. not in pythonw or --noconsole)
    if sys.stdout is not None:
        try:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(numeric_level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        except Exception:
            pass

    _LOGGING_INITIALIZED = True
    logger.info("Logging initialized at %s (level=%s, release_mode=%s)", log_path, level, is_release_mode())
    return logger


def get_logger(name: str = "astrarun") -> logging.Logger:
    """Retrieve logger instance."""
    return logging.getLogger(name)
