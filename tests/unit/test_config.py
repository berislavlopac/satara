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


@pytest.mark.parametrize("name", ["MAX_FILES", "MAX_FILE_SIZE", "MAX_TOTAL_SIZE"])
def test_settings_refuse_a_limit_of_zero(monkeypatch, name):
    monkeypatch.setenv(f"SATARA_{name}", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_refuse_more_than_a_thousand_files(monkeypatch):
    monkeypatch.setenv("SATARA_MAX_FILES", "1001")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_accept_a_thousand_files(monkeypatch):
    monkeypatch.setenv("SATARA_MAX_FILES", "1000")

    settings = Settings(_env_file=None)

    assert settings.MAX_FILES == 1000


def test_settings_leave_the_deferred_flow_off_by_default():
    settings = Settings(_env_file=None)

    assert settings.DEFERRED_ENABLED is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [("PT2H", timedelta(hours=2)), ("00:15:00", timedelta(minutes=15))],
    ids=["ISO 8601 duration", "hours, minutes and seconds"],
)
def test_settings_read_a_URL_lifetime_as_a_duration_or_a_time(monkeypatch, value, expected):
    monkeypatch.setenv("SATARA_PRESIGNED_URL_LIFETIME", value)

    settings = Settings(_env_file=None)

    assert settings.PRESIGNED_URL_LIFETIME == expected


@pytest.mark.parametrize("value", ["0", "P8D"], ids=["zero", "over seven days"])
def test_settings_refuse_a_URL_lifetime_of_zero_or_over_seven_days(monkeypatch, value):
    monkeypatch.setenv("SATARA_PRESIGNED_URL_LIFETIME", value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_refuse_a_deferred_file_size_over_the_largest_single_upload(monkeypatch):
    monkeypatch.setenv("SATARA_DEFERRED_MAX_FILE_SIZE", str(5 * GIB + 1))

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_allow_deferred_archives_more_than_direct_ones():
    settings = Settings(_env_file=None)

    direct = (settings.MAX_FILES, settings.MAX_FILE_SIZE, settings.MAX_TOTAL_SIZE)
    deferred = (
        settings.DEFERRED_MAX_FILES,
        settings.DEFERRED_MAX_FILE_SIZE,
        settings.DEFERRED_MAX_TOTAL_SIZE,
    )
    assert all(more > less for more, less in zip(deferred, direct, strict=True))
