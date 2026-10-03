"""Structured logging for the whole process, configured when this module is imported."""

import logging
import os

import structlog
import unclogger
from unclogger.defaults import json_default

DEBUG = os.environ.get("SATARA_DEBUG", "").lower() == "true"
"""Whether to log everything at debug level, read from `SATARA_DEBUG`.

Logging is configured on import, before any settings are read, so it reads the variable behind
the `DEBUG` setting directly.
"""

# Noisy third-party loggers, held at warning level outside debug mode.
_THIRD_PARTY_LOGGERS = ("aiobotocore", "botocore", "urllib3")

# The web server's loggers. Their records do not pass through structlog, so they have a handler
# of their own that renders them as the service's own logs are rendered.
_SERVER_LOGGERS = ("uvicorn.access", "uvicorn.error")


def configure_logging(debug: bool = DEBUG) -> None:
    """Configure logging for the whole process.

    Renders the web server's logs as JSON too. Outside debug mode it logs at info level and
    holds noisy third-party loggers at warning; in debug mode every logger logs at debug
    level. Each call configures afresh, so it can be called again.

    Args:
        debug: Whether to log everything at debug level.
    """
    level = logging.DEBUG if debug else logging.INFO
    for name in _THIRD_PARTY_LOGGERS:
        logging.getLogger(name).setLevel(logging.DEBUG if debug else logging.WARNING)
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
        server_logger.setLevel(level)
    unclogger.set_level(level)


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

    The logger has no level of its own and follows the root logger's, so configuring logging
    again later, as from the settings, also changes the loggers already made.

    Args:
        name: The logger's name, by convention the module's `__name__`.
    """
    return unclogger.get_logger(name, level=logging.NOTSET)


configure_logging()
