"""Structured logging configuration for AstraRun."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


_LOGGING_INITIALIZED = False


def setup_logging(
    log_file: str | Path = "logs/astrarun.log",
    level: str = "INFO",
    max_bytes: int = 10_485_760,
    backup_count: int = 3,
) -> logging.Logger:
    """Initialize structured rotating file and console logging."""
    global _LOGGING_INITIALIZED
    logger = logging.getLogger("astrarun")

    if _LOGGING_INITIALIZED:
        return logger

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

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

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    _LOGGING_INITIALIZED = True
    logger.info("Logging initialized at %s (level=%s)", log_path, level)
    return logger


def get_logger(name: str = "astrarun") -> logging.Logger:
    """Retrieve logger instance."""
    return logging.getLogger(name)
