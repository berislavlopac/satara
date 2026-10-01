from pydantic import ValidationError
import pytest

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
