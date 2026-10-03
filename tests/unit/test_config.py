import pytest
from pydantic import ValidationError

from satara.config import MIB, Settings


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


@pytest.mark.parametrize(
    ("name", "value"),
    [("MAX_FILES", "1001"), ("MAX_FILE_SIZE", "2001MiB")],
    ids=["files", "file size"],
)
def test_settings_refuse_a_limit_above_the_highest_allowed(monkeypatch, name, value):
    monkeypatch.setenv(f"SATARA_{name}", value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_accept_limits_at_the_highest_allowed(monkeypatch):
    monkeypatch.setenv("SATARA_MAX_FILES", "1000")
    monkeypatch.setenv("SATARA_MAX_FILE_SIZE", "2000MiB")

    settings = Settings(_env_file=None)

    assert (settings.MAX_FILES, settings.MAX_FILE_SIZE) == (1000, 2000 * MIB)
