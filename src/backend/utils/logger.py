"""Structured logging configuration with JSON formatting and correlation IDs."""

import json
import logging
import sys
import uuid
from typing import Any

from src.backend.config import settings


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log string
        """
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation ID if present
        if hasattr(record, "correlation_id"):
            log_data["correlation_id"] = record.correlation_id

        # Add request ID if present
        if hasattr(record, "request_id"):
            log_data["request_id"] = str(record.request_id)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data, default=str)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with structured JSON formatting.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # Avoid adding duplicate handlers
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    return logger


def add_correlation_id(logger: logging.Logger, correlation_id: str | None = None) -> str:
    """
    Add correlation ID to logger context.

    Args:
        logger: Logger instance
        correlation_id: Correlation ID (generates UUID if not provided)

    Returns:
        Correlation ID used
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    # Store in logger context using adapter pattern
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = old_factory(*args, **kwargs)
        record.correlation_id = correlation_id
        return record

    logging.setLogRecordFactory(record_factory)

    return correlation_id

