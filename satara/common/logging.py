"""Structured logging, configured once for the whole process."""

import logging
import os

import unclogger

DEBUG = os.environ.get("SATARA_DEBUG", "").lower() == "true"
"""Whether to log at debug level, read from `SATARA_DEBUG`."""

# Noisy third-party loggers, held at warning level unless actively debugging them.
_THIRD_PARTY_LOGGERS = ("aiobotocore", "botocore", "urllib3")

_configured = False


def configure_logging() -> None:
    """Set the level from `SATARA_DEBUG` and quieten noisy third-party loggers.

    Idempotent; runs once when this module is imported.
    """
    global _configured
    if _configured:
        return
    for name in _THIRD_PARTY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    unclogger.set_level(logging.DEBUG if DEBUG else logging.INFO)
    _configured = True


def get_logger(name: str) -> unclogger.Unclogger:
    """Return a structured logger, used like a standard one.

    Args:
        name: The logger's name, by convention the module's `__name__`.
    """
    return unclogger.get_logger(name, level=logging.DEBUG if DEBUG else logging.INFO)


configure_logging()
