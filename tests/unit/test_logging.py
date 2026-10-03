import json
import logging

import satara.common.logging  # noqa: F401 - configures logging when imported


def test_web_server_logs_are_rendered_as_JSON(caplog):
    """Renders the server's records in the service's own form, though they skip structlog.

    The record is captured, then formatted by the server logger's own handler: the captured
    text is in the test runner's format, not the one under test.
    """
    access = logging.getLogger("uvicorn.access")
    with caplog.at_level(logging.INFO, logger=access.name):
        access.info('%s - "%s %s HTTP/%s" %d', "10.0.0.1:5000", "GET", "/health", "1.1", 200)

    [record] = caplog.records
    rendered = json.loads(access.handlers[0].format(record))

    assert rendered.keys() == {"event", "logger", "level", "timestamp"}
    assert (rendered["event"], rendered["logger"], rendered["level"]) == (
        '10.0.0.1:5000 - "GET /health HTTP/1.1" 200',
        "uvicorn.access",
        "info",
    )
