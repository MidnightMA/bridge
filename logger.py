"""Structured logging configuration."""

import logging
import sys


def setup_logger(name: str = "bridge", log_level: str = "INFO") -> logging.Logger:
    """Configures and returns a structured logger.

    Args:
        name: The logger instance name.
        log_level: The logging severity level.

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(name)
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger