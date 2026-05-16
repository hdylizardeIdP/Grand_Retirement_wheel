"""Logging setup. One call from the CLI entry point; modules just use logging.getLogger(__name__)."""

from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger with a stderr handler and a consistent format."""
    raise NotImplementedError


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper around ``logging.getLogger``."""
    return logging.getLogger(name)
