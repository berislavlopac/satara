import json
import logging

import pytest

from satara.common.logging import configure_logging, silence_access_log


def test_web_server_logs_are_rendered_as_JSON(caplog):
    """Renders the server's records in the service's own form, though they skip structlog.

    The record is captured, then formatted by the server logger's own handler: the captured
    text is in the test runner's format, not the one under test.
    """
    access = logging.getLogger("uvicorn.access")
    with caplog.at_level(logging.INFO, logger=access.name):
        access.info('%s - "%s %s HTTP/%s" %d', "10.0.0.1:5000", "GET", "/archives", "1.1", 200)

    [record] = caplog.records
    rendered = json.loads(access.handlers[0].format(record))

    assert rendered.keys() == {"event", "logger", "level", "timestamp"}
    assert (rendered["event"], rendered["logger"], rendered["level"]) == (
        '10.0.0.1:5000 - "GET /archives HTTP/1.1" 200',
        "uvicorn.access",
        "info",
    )


def test_web_server_access_log_leaves_out_a_silenced_path(caplog):
    access = logging.getLogger("uvicorn.access")
    silence_access_log("/health")

    with caplog.at_level(logging.INFO, logger=access.name):
        for path in ["/health", "/health?verbose=1", "/archives", "/healthy"]:
            access.info('%s - "%s %s HTTP/%s" %d', "10.0.0.1:5000", "GET", path, "1.1", 200)

    paths = [record.args[2] for record in caplog.records]
    assert paths == ["/archives", "/healthy"]


@pytest.fixture
def logging_configured_for():
    """Configure logging for or against debug mode, and restore the default afterwards."""
    yield configure_logging
    configure_logging(debug=False)


@pytest.mark.parametrize(
    ("debug", "expected"),
    [(True, logging.DEBUG), (False, logging.WARNING)],
    ids=["debug mode", "otherwise"],
)
def test_logging_lowers_the_loggers_of_libraries_only_in_debug_mode(
    logging_configured_for, debug, expected
):
    logging_configured_for(debug=debug)

    levels = {logging.getLogger(name).level for name in ["botocore", "aiobotocore", "urllib3"]}

    assert levels == {expected}


def test_logging_logs_everything_at_debug_level_in_debug_mode(logging_configured_for):
    logging_configured_for(debug=True)

    levels = {
        logging.getLogger(name).getEffectiveLevel()
        for name in ["satara.anything", "uvicorn.access", "uvicorn.error"]
    }

    assert levels == {logging.DEBUG}
