import json
import logging

import satara.common.logging  # noqa: F401 - configures logging when imported


def test_web_server_logs_are_rendered_as_JSON():
    """Renders the server's records in the service's own form, though they skip structlog.

    The record is formatted by the logger's handler directly: the handler writes to the
    stream that was standard error when it was made, which pytest had replaced by then.
    """
    access = logging.getLogger("uvicorn.access")
    record = access.makeRecord(
        access.name,
        logging.INFO,
        "uvicorn/protocols/http/h11_impl.py",
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("10.0.0.1:5000", "GET", "/health", "1.1", 200),
        None,
    )

    rendered = json.loads(access.handlers[0].format(record))

    assert rendered.keys() == {"event", "logger", "level", "timestamp"}
    assert (rendered["event"], rendered["logger"], rendered["level"]) == (
        '10.0.0.1:5000 - "GET /health HTTP/1.1" 200',
        "uvicorn.access",
        "info",
    )
