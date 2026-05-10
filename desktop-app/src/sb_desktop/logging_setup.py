"""Centralised logging setup.

Logs land in two places:

* stderr (configurable verbosity) — useful when running headless or under
  PyInstaller console builds.
* A rotating file in the per-platform user data directory — survives
  app restarts and is what the in-app log viewer reads from.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from .paths import log_file_path

_LOG_FORMAT = "%(asctime)s [%(levelname)-7s] %(name)s :: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 2 * 1024 * 1024
_BACKUP_COUNT = 5

_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Idempotent root logger configuration.

    Calling more than once is safe — handlers are only attached on the first
    call. Subsequent calls update the level on the existing handlers.
    """
    global _configured

    root = logging.getLogger()
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(numeric_level)

    if _configured:
        for handler in root.handlers:
            handler.setLevel(numeric_level)
        return

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    stderr_handler = logging.StreamHandler(stream=sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(numeric_level)
    root.addHandler(stderr_handler)

    log_path = log_file_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    _configured = True
