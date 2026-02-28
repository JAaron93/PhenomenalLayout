"""Central logging configuration for Dolphin OCR components.

Provides a single setup function and a helper to get namespaced loggers.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
_log_env = os.getenv("LOG_FILE", "").strip()
_DEFAULT_LOG_PATH = (
    Path(_log_env).expanduser() if _log_env else (Path("logs") / "app.log")
)
# Expose the default as a string for compatibility with callers
DEFAULT_LOG_FILE = str(_DEFAULT_LOG_PATH)
DEFAULT_LOGGER_NAME = "dolphin_ocr"


def setup_logging(
    *,
    level: str = DEFAULT_LOG_LEVEL,
    log_file: Optional[str | Path] = DEFAULT_LOG_FILE,
    logger_name: str = DEFAULT_LOGGER_NAME,
) -> logging.Logger:
    """Configure root logger for the Dolphin OCR system.

    Creates console and optional file handlers with a consistent format.
    Idempotent: repeated calls won't duplicate handlers.
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, level, logging.INFO))

    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")

    # Console handler
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        logger.addHandler(console)

    # File handler
    if log_file:
        try:
            path = Path(log_file)
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Best-effort directory creation; fallback to console-only
            log_file = None

    if log_file:
        desired = Path(log_file).resolve()
        for h in list(logger.handlers):
            if isinstance(h, logging.FileHandler):
                current = getattr(h, "baseFilename", None)
                if current and Path(current).resolve() != desired:
                    logger.removeHandler(h)
                    try:
                        h.close()
                    except Exception:
                        pass

        if not any(
            isinstance(h, logging.FileHandler)
            and Path(getattr(h, "baseFilename", ".")).resolve() == desired
            for h in logger.handlers
        ):
            file_handler = logging.FileHandler(str(desired))
            file_handler.setFormatter(fmt)
            logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the Dolphin OCR namespace."""
    parent = logging.getLogger(DEFAULT_LOGGER_NAME)
    if not parent.handlers:
        setup_logging()
    return parent.getChild(name)
