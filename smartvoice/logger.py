"""Centralized logging for SmartVoice.

Usage:
    from smartvoice.logger import get_logger
    log = get_logger(__name__)
    log.info("Processing call %d", call_id)
    log.exception("STT failed")    # inside except block — logs full traceback

Log destinations:
    - Console (INFO+)
    - File: data/logs/smartvoice.log (rotated at 5MB, keep 3 backups)

Control log level with env var: SMARTVOICE_LOG_LEVEL (default: INFO)
"""

import logging
import logging.handlers
import os
import sys

_LOG_DIR = os.path.join("data", "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "smartvoice.log")
_FORMAT = "%(asctime)s  %(levelname)-7s  %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
_configured = False


def _configure_root() -> None:
    """Configure root logger once per process."""
    global _configured
    if _configured:
        return
    _configured = True

    os.makedirs(_LOG_DIR, exist_ok=True)
    level_name = os.getenv("SMARTVOICE_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger("smartvoice")
    root.setLevel(level)
    root.propagate = False

    # Avoid duplicate handlers on Streamlit re-import
    if root.handlers:
        return

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            _LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # If the file handler fails (permissions, read-only FS), keep console only
        root.warning("Could not open log file %s — console logging only", _LOG_FILE)


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger rooted under 'smartvoice'."""
    _configure_root()
    if not name.startswith("smartvoice"):
        name = f"smartvoice.{name}"
    return logging.getLogger(name)
