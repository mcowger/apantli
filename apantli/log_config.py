import logging
import sys
from typing import Optional, Any

# Check if colorlog is available at module level
try:
    from colorlog import ColoredFormatter
    COLOR_AVAILABLE = True
except ImportError:
    COLOR_AVAILABLE = False

# Module-level logger export
logger: logging.Logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Return a configured logger with consistent formatting and optional color support.
    """

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid adding multiple handlers if logger already configured
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)

    timestamp_format = "%Y-%m-%d %H:%M:%S"
    log_format = "%(asctime)s %(levelname)s:     %(message)s"

    if COLOR_AVAILABLE:
        formatter = ColoredFormatter( # pyright: ignore[reportPossiblyUnboundVariable]
            "%(log_color)s%(asctime)s %(levelname)s:%(reset)s     %(message)s",
            datefmt=timestamp_format,
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        )
    else:
        formatter = logging.Formatter(log_format, datefmt=timestamp_format)

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


# Initialize default module-level logger
logger = get_logger(__name__)


def get_uvicorn_config(log_level: str = "info") -> dict[str, Any]:
    """
    Get uvicorn logging configuration that matches the custom log format.
    
    Args:
        log_level: Logging level (debug, info, warning, error, critical)
    
    Returns:
        Dictionary with uvicorn logging configuration
    """
    timestamp_format = "%Y-%m-%d %H:%M:%S"
    log_format = "%(asctime)s %(levelname)s:     %(message)s"
    
    # Uvicorn's logging configuration dictionary
    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": log_format,
                "datefmt": timestamp_format,
            },
            "access": {
                "format": log_format,
                "datefmt": timestamp_format,
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": log_level.upper()},
            "uvicorn.error": {"level": log_level.upper()},
            "uvicorn.access": {"handlers": ["access"], "level": log_level.upper(), "propagate": False},
        },
    }
    
    # Add color support if available
    if COLOR_AVAILABLE:
        config["formatters"]["default"] = {
            "()": "colorlog.ColoredFormatter",
            "format": "%(log_color)s%(asctime)s %(levelname)s:%(reset)s     %(message)s",
            "datefmt": timestamp_format,
            "log_colors": {
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        }
        config["formatters"]["access"] = {
            "()": "colorlog.ColoredFormatter",
            "format": "%(log_color)s%(asctime)s %(levelname)s:%(reset)s     %(message)s",
            "datefmt": timestamp_format,
            "log_colors": {
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        }
    
    return config
