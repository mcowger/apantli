import logging
import sys
from typing import Optional


# Module-level logger export
logger: logging.Logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Return a configured logger with consistent formatting and optional color support.
    """
    try:
        from colorlog import ColoredFormatter
        COLOR_AVAILABLE = True
    except ImportError:
        COLOR_AVAILABLE = False

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
