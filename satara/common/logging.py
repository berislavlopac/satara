"""Structured logging, configured once for the whole process."""

import logging
import os

import structlog
import unclogger
from unclogger.defaults import json_default

DEBUG = os.environ.get("SATARA_DEBUG", "").lower() == "true"
"""Whether to log at debug level, read from `SATARA_DEBUG`."""

# Noisy third-party loggers, held at warning level unless actively debugging them.
_THIRD_PARTY_LOGGERS = ("aiobotocore", "botocore", "urllib3")

# The web server's loggers. Their records do not pass through structlog, so they have a handler
# of their own that renders them as the service's own logs are rendered.
_SERVER_LOGGERS = ("uvicorn.access", "uvicorn.error")

_configured = False


def configure_logging() -> None:
    """Configure logging for the whole process, once.

    Sets the level from `SATARA_DEBUG`, quietens noisy third-party loggers, and renders the web
    server's logs as JSON too. Idempotent; runs when this module is imported.
    """
    global _configured
    if _configured:
        return
    for name in _THIRD_PARTY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    handler = logging.StreamHandler()
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=[
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
            ],
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(default=json_default),
            ],
        )
    )
    for name in _SERVER_LOGGERS:
        server_logger = logging.getLogger(name)
        server_logger.handlers = [handler]
        server_logger.propagate = False
    unclogger.set_level(logging.DEBUG if DEBUG else logging.INFO)
    _configured = True


def get_logger(name: str) -> unclogger.Unclogger:
    """Return a structured logger, used like a standard one.

    Args:
        name: The logger's name, by convention the module's `__name__`.
    """
    return unclogger.get_logger(name, level=logging.DEBUG if DEBUG else logging.INFO)


configure_logging()
