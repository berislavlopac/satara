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


class _AccessPathFilter(logging.Filter):
    """Drops the access log records of requests for one path, with or without a query."""

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def filter(self, record: logging.LogRecord) -> bool:
        # The server's access records carry the client, method, path, HTTP version and status.
        args = record.args if isinstance(record.args, tuple) else ()
        return len(args) < 3 or str(args[2]).partition("?")[0] != self._path  # noqa: PLR2004

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _AccessPathFilter) and other._path == self._path

    def __hash__(self) -> int:
        return hash(self._path)


def silence_access_log(path: str) -> None:
    """Leave requests for `path` out of the web server's access log.

    Idempotent: a path silenced twice is filtered once.
    """
    logging.getLogger("uvicorn.access").addFilter(_AccessPathFilter(path))


def get_logger(name: str) -> unclogger.Unclogger:
    """Return a structured logger, used like a standard one.

    Args:
        name: The logger's name, by convention the module's `__name__`.
    """
    return unclogger.get_logger(name, level=logging.DEBUG if DEBUG else logging.INFO)


configure_logging()
