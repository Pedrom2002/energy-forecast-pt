"""
Structured logging configuration with JSON support
"""
import logging
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON

        Args:
            record: Log record to format

        Returns:
            JSON formatted log string
        """
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        # Add custom fields from record
        for key, value in record.__dict__.items():
            if key not in ("name", "msg", "args", "created", "filename", "funcName",
                          "levelname", "lineno", "module", "msecs", "message",
                          "pathname", "process", "processName", "relativeCreated",
                          "thread", "threadName", "exc_info", "exc_text", "stack_info",
                          "extra_fields"):
                log_data[key] = value

        return json.dumps(log_data, ensure_ascii=False)


class HumanFormatter(logging.Formatter):
    """
    Human-readable formatter for console output
    """

    # Color codes
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record with colors (if terminal supports it)

        Args:
            record: Log record to format

        Returns:
            Formatted log string
        """
        # Check if output is a terminal
        use_colors = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()

        if use_colors:
            color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
            reset = self.COLORS['RESET']
            record.levelname = f"{color}{record.levelname}{reset}"

        return super().format(record)


def setup_logger(
    name: str,
    log_dir: str = "logs",
    level: int = logging.INFO,
    json_format: bool = False,
    console_output: bool = True,
    file_output: bool = True
) -> logging.Logger:
    """
    Configure and return a structured logger instance

    Args:
        name: Logger name
        log_dir: Directory for log files
        level: Logging level
        json_format: Use JSON format for logs (recommended for production)
        console_output: Enable console output
        file_output: Enable file output

    Returns:
        Configured logger instance

    Example:
        >>> logger = setup_logger("api", json_format=True)
        >>> logger.info("User logged in", extra={"user_id": 123, "ip": "127.0.0.1"})
    """
    # Create logs directory
    if file_output:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Remove existing handlers
    logger.handlers.clear()

    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)

        if json_format:
            console_formatter = JSONFormatter()
        else:
            console_formatter = HumanFormatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )

        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    # File handler
    if file_output:
        log_file = log_path / f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)

        # Always use JSON format for files (easier to parse)
        file_formatter = JSONFormatter()
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def log_function_call(logger: logging.Logger):
    """
    Decorator to log function calls with parameters

    Args:
        logger: Logger instance to use

    Example:
        >>> logger = setup_logger("my_module")
        >>> @log_function_call(logger)
        >>> def my_function(x, y):
        >>>     return x + y
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger.debug(
                f"Calling {func.__name__}",
                extra={
                    "function": func.__name__,
                    "args": str(args),
                    "kwargs": str(kwargs)
                }
            )

            try:
                result = func(*args, **kwargs)
                logger.debug(
                    f"Function {func.__name__} completed",
                    extra={"function": func.__name__}
                )
                return result
            except Exception as e:
                logger.error(
                    f"Function {func.__name__} failed",
                    extra={
                        "function": func.__name__,
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )
                raise

        return wrapper
    return decorator


# Convenience function for API logging
def log_request(logger: logging.Logger, endpoint: str, method: str, **kwargs):
    """
    Log API request with structured data

    Args:
        logger: Logger instance
        endpoint: API endpoint
        method: HTTP method
        **kwargs: Additional fields (user_id, ip_address, etc.)
    """
    log_data = {
        "event": "api_request",
        "endpoint": endpoint,
        "method": method,
        **kwargs
    }

    logger.info(f"API Request: {method} {endpoint}", extra=log_data)


def log_prediction(logger: logging.Logger, model_name: str, prediction: float,
                   latency_ms: float, **kwargs):
    """
    Log model prediction with structured data

    Args:
        logger: Logger instance
        model_name: Name of the model used
        prediction: Predicted value
        latency_ms: Prediction latency in milliseconds
        **kwargs: Additional fields (region, timestamp, etc.)
    """
    log_data = {
        "event": "model_prediction",
        "model": model_name,
        "prediction": prediction,
        "latency_ms": latency_ms,
        **kwargs
    }

    logger.info(f"Prediction made by {model_name}", extra=log_data)


# Example usage
if __name__ == "__main__":
    # Console-friendly logger (development)
    dev_logger = setup_logger("dev", json_format=False)
    dev_logger.info("Application started in development mode")
    dev_logger.debug("Debug information", extra={"debug_level": 1})
    dev_logger.warning("This is a warning")
    dev_logger.error("Error occurred", extra={"error_code": 500})

    # JSON logger (production)
    prod_logger = setup_logger("prod", json_format=True, console_output=False)
    prod_logger.info("Application started in production mode",
                     extra={"version": "1.0.0", "environment": "production"})

    # API request logging
    log_request(prod_logger, "/predict", "POST", user_id=123, ip="192.168.1.1")

    # Prediction logging
    log_prediction(prod_logger, "XGBoost", 2500.5, 45.2,
                   region="Lisboa", confidence=0.95)
