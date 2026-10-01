from datetime import UTC, datetime
from uuid import UUID


def validate_uuid7(value: UUID | str | int) -> UUID:
    """Validates and converts the input value to an UUID7 instance.

    Args:
        value: Input value to validate and convert.

    Returns:
        UUID instance of version 7.

    Raises:
        ValueError: The input is not a UUID, or is a UUID of another version.
            The message names which, in the wording the validation library uses
            for its own errors, and never repeats the input.
    """
    try:
        if isinstance(value, str):
            value = UUID(value)
        if isinstance(value, int):
            value = UUID(int=value)
    except ValueError:
        raise ValueError("Input should be a valid UUID") from None
    if value.version != 7:  # noqa: PLR2004
        raise ValueError("Input should be a uuid7")
    return value


def ensure_utc_datetime(value: object) -> datetime:
    """Ensures that the input value is a datetime instance with UTC timezone.

    Every datetime inside the system is UTC. A naive datetime is read as UTC and an
    aware one is converted to it. Anything else is refused rather than parsed: any
    parsing belongs where a value enters the system, and should refuse timezone
    abbreviations, which collide (`BST` is both British Summer Time and Bangladesh
    Standard Time).

    Args:
        value: Input value to validate and convert.

    Returns:
        A datetime instance with UTC timezone.

    Raises:
        ValueError: The value is not a datetime.
    """
    if not isinstance(value, datetime):
        message = f"Expected a datetime, got {type(value).__name__}"
        # A ValueError, not a TypeError: validation reports only the former as invalid input.
        raise ValueError(message)  # noqa: TRY004
    if value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
