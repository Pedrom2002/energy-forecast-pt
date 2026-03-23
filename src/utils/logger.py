"""Structured logging configuration with JSON support.

Features:
    - JSON format for production (machine-readable, integrates with log
      aggregators)
    - Human-readable coloured format for development (TTY detection)
    - Timed rotating file handler with 30-day retention
    - Optional request ID propagation via contextvars for async request
      tracing
    - Log level configurable via ``LOG_LEVEL`` environment variable
    - Slow-call helper: :func:`log_slow_call` context manager that emits a
      WARNING when a block exceeds a configurable threshold
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Any

# Context variable for request ID -- set this in middleware to trace requests
# through async log calls without passing it explicitly everywhere.
_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

# Default log level from environment (INFO if not set or unrecognised).
_ENV_LOG_LEVEL: int = getattr(
    logging,
    os.environ.get("LOG_LEVEL", "INFO").upper(),
    logging.INFO,
)


def set_request_id(request_id: str) -> None:
    """Set the request ID for the current async context.

    Args:
        request_id: Unique identifier for the current request.
    """
    _request_id.set(request_id)


def get_request_id() -> str:
    """Get the current request ID, or empty string if not set.

    Returns:
        The request ID string for the current context.
    """
    return _request_id.get()


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging.

    Includes ``request_id`` from the current async context when available,
    enabling full request tracing across async log calls.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string.

        Args:
            record: The log record to format.

        Returns:
            JSON-encoded string representation of the log record.
        """
        log_data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        request_id = get_request_id()
        if request_id:
            log_data["request_id"] = request_id

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data, ensure_ascii=False)


class HumanFormatter(logging.Formatter):
    """Human-readable formatter with optional color output."""

    COLORS: dict[str, str] = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
        "RESET": "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record with optional ANSI colour codes.

        Args:
            record: The log record to format.

        Returns:
            Formatted string, colourised when outputting to a TTY.
        """
        use_colors = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
        if use_colors:
            color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
            reset = self.COLORS["RESET"]
            record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


def setup_logger(
    name: str,
    log_dir: str = "logs",
    level: int | None = None,
    json_format: bool = False,
    console_output: bool = True,
    file_output: bool = True,
    backup_count: int = 30,
    max_bytes: int = 0,
) -> logging.Logger:
    """Configure and return a structured logger instance.

    The effective log *level* follows this priority:

    1. The explicit ``level`` argument (when not None).
    2. The ``LOG_LEVEL`` environment variable (e.g. ``LOG_LEVEL=DEBUG``).
    3. ``logging.INFO`` as the final default.

    File rotation strategy:

    - If ``max_bytes > 0``: uses :class:`RotatingFileHandler` (size-based).
    - Otherwise: uses :class:`TimedRotatingFileHandler` (time-based, daily).

    Args:
        name: Logger name (used as the log file base name).
        log_dir: Directory for log files.  Created if it does not exist.
        level: Logging level override.  When ``None`` the ``LOG_LEVEL`` env
            var is used (default ``logging.INFO``).
        json_format: Use JSON format (recommended for production / log
            aggregation).
        console_output: Whether to emit logs to stdout.
        file_output: Whether to write logs to a rotating file.
        backup_count: Number of rotated files to retain (default 30).
        max_bytes: Maximum file size in bytes before rotation (0 = time-based
            only).  Suggested value for production: ``50 * 1024 * 1024``
            (50 MB).

    Returns:
        Configured :class:`logging.Logger` instance.
    """
    effective_level = level if level is not None else _ENV_LOG_LEVEL

    log_path: Path | None = None
    if file_output:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

    logger_inst = logging.getLogger(name)
    logger_inst.setLevel(effective_level)
    logger_inst.handlers.clear()

    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(effective_level)
        if json_format:
            console_handler.setFormatter(JSONFormatter())
        else:
            console_handler.setFormatter(
                HumanFormatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
        logger_inst.addHandler(console_handler)

    if file_output and log_path is not None:
        log_file = log_path / f"{name}.log"
        if max_bytes > 0:
            file_handler: logging.Handler = RotatingFileHandler(
                str(log_file),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
        else:
            file_handler = TimedRotatingFileHandler(
                str(log_file),
                when="midnight",
                backupCount=backup_count,
                encoding="utf-8",
            )
        file_handler.setLevel(effective_level)
        file_handler.setFormatter(JSONFormatter())
        logger_inst.addHandler(file_handler)

    return logger_inst


def log_function_call(logger_inst: logging.Logger) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that logs function entry, exit, and any exceptions.

    Logs at DEBUG level for normal entry/exit and ERROR level on exception.

    Args:
        logger_inst: Logger to emit messages on.

    Returns:
        A decorator function.
    """
    import functools

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger_inst.debug("Calling %s", func.__name__)
            try:
                result = func(*args, **kwargs)
                logger_inst.debug("Completed %s", func.__name__)
                return result
            except Exception as exc:
                logger_inst.error("Failed %s: %s", func.__name__, exc, exc_info=True)
                raise

        return wrapper

    return decorator


@contextmanager
def log_slow_call(
    logger_inst: logging.Logger,
    operation: str,
    threshold_ms: float = 1000.0,
    extra: dict[str, Any] | None = None,
) -> Generator[None, None, None]:
    """Context manager that logs a WARNING when the enclosed block is slow.

    Example::

        with log_slow_call(logger, "feature_engineering", threshold_ms=500):
            df_features = fe.create_all_features(df)

    Args:
        logger_inst: Logger to emit the warning on.
        operation: Human-readable name of the operation (included in the log).
        threshold_ms: Duration in milliseconds above which a WARNING is
            emitted (default 1000 ms).  Set to 0 to always log at DEBUG
            level.
        extra: Optional additional fields to include in the log record's
            ``extra_fields`` dict (picked up by :class:`JSONFormatter`).

    Yields:
        Nothing -- the context manager just wraps timing.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        fields: dict[str, Any] = {
            "operation": operation,
            "duration_ms": round(elapsed_ms, 2),
            "threshold_ms": threshold_ms,
            **(extra or {}),
        }
        if elapsed_ms > threshold_ms:
            logger_inst.warning(
                "SLOW OPERATION '%s' took %.1f ms (threshold %.0f ms)",
                operation,
                elapsed_ms,
                threshold_ms,
                extra={"extra_fields": fields},
            )
        else:
            logger_inst.debug(
                "Operation '%s' completed in %.1f ms",
                operation,
                elapsed_ms,
                extra={"extra_fields": fields},
            )
