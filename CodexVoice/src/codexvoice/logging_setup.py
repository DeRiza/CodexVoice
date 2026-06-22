"""Logging setup for CodexVoice."""

from __future__ import annotations

import logging
from pathlib import Path

from .config import LoggingConfig


def default_log_dir() -> Path:
    return Path.home() / "Library" / "Logs" / "CodexVoice"


def setup_logging(config: LoggingConfig, log_dir: Path | None = None) -> logging.Logger:
    directory = log_dir or default_log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / "codexvoice.log"

    logger = logging.getLogger("codexvoice")
    logger.setLevel(config.level.upper())
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger

