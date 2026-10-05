from datetime import timedelta

import pytest
from pydantic import ValidationError

from satara.config import GIB, MIB, Settings


def test_settings_read_limits_from_prefixed_environment_variables(monkeypatch):
    monkeypatch.setenv("SATARA_MAX_FILES", "7")
    monkeypatch.setenv("MAX_FILES", "9")

    settings = Settings(_env_file=None)

    assert settings.MAX_FILES == 7


@pytest.mark.parametrize(
    ("value", "expected"),
    [("10MiB", 10 * MIB), ("10MB", 10_000_000), ("1024", 1024)],
    ids=["binary unit", "decimal unit", "no unit"],
)
def test_settings_read_sizes_with_or_without_a_unit(monkeypatch, value, expected):
    monkeypatch.setenv("SATARA_MAX_FILE_SIZE", value)

    settings = Settings(_env_file=None)

    assert settings.MAX_FILE_SIZE == expected


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MAX_FILES", "0"),
        ("MAX_FILE_SIZE", "0"),
        ("MAX_TOTAL_SIZE", "0"),
        ("MAX_FILES", "1001"),
        ("DEFERRED_MAX_FILES", "10001"),
        ("DEFERRED_MAX_FILE_SIZE", str(5 * GIB + 1)),
        ("DEFERRED_MAX_TOTAL_SIZE", str(150 * GIB + 1)),
        ("PRESIGNED_URL_LIFETIME", "0"),
        ("PRESIGNED_URL_LIFETIME", "P8D"),
    ],
    ids=[
        "a file count of zero",
        "a file size of zero",
        "a total size of zero",
        "more files than the form parser takes",
        "more than ten thousand deferred files",
        "a file over the largest single upload",
        "a total over what storage takes",
        "a URL lifetime of zero",
        "a URL lifetime over seven days",
    ],
)
def test_settings_refuse_a_value_outside_its_bounds(monkeypatch, name, value):
    monkeypatch.setenv(f"SATARA_{name}", value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_accept_a_thousand_files(monkeypatch):
    monkeypatch.setenv("SATARA_MAX_FILES", "1000")

    settings = Settings(_env_file=None)

    assert settings.MAX_FILES == 1000


def test_settings_leave_the_deferred_flow_and_debug_mode_off_by_default(monkeypatch):
    monkeypatch.delenv("SATARA_DEFERRED_ENABLED", raising=False)
    monkeypatch.delenv("SATARA_DEBUG", raising=False)

    settings = Settings(_env_file=None)

    assert (settings.DEFERRED_ENABLED, settings.DEBUG) == (False, False)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("PT2H", timedelta(hours=2)), ("00:15:00", timedelta(minutes=15))],
    ids=["ISO 8601 duration", "hours, minutes and seconds"],
)
def test_settings_read_a_URL_lifetime_as_a_duration_or_a_time(monkeypatch, value, expected):
    monkeypatch.setenv("SATARA_PRESIGNED_URL_LIFETIME", value)

    settings = Settings(_env_file=None)

    assert settings.PRESIGNED_URL_LIFETIME == expected


def test_settings_allow_deferred_archives_more_than_direct_ones():
    settings = Settings(_env_file=None)

    direct = (settings.MAX_FILES, settings.MAX_FILE_SIZE, settings.MAX_TOTAL_SIZE)
    deferred = (
        settings.DEFERRED_MAX_FILES,
        settings.DEFERRED_MAX_FILE_SIZE,
        settings.DEFERRED_MAX_TOTAL_SIZE,
    )
    assert all(more > less for more, less in zip(deferred, direct, strict=True))
