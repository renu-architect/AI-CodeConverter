"""Structured JSON logging for AI-SDLC framework."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_fields") and record.extra_fields:
            log_entry.update(record.extra_fields)
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure structured JSON logging and return root logger."""
    root_logger = logging.getLogger("ai_sdlc")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        root_logger.addHandler(handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a named child logger under the ai_sdlc namespace."""
    return logging.getLogger(f"ai_sdlc.{name}")


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    **kwargs: Any,
) -> None:
    """Log a message with additional structured context fields."""
    record = logger.makeRecord(
        logger.name, level, "(unknown)", 0, message, (), None
    )
    record.extra_fields = kwargs  # type: ignore[attr-defined]
    logger.handle(record)
