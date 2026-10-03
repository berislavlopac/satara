"""Validators for values that enter models from outside."""

from uuid import UUID


def validate_uuid7(value: object) -> UUID:
    """Validates and converts the input value to an UUID7 instance.

    Args:
        value: Input value to validate and convert: a UUID, or a string holding one.

    Returns:
        UUID instance of version 7.

    Raises:
        ValueError: The input is not a UUID, or is a UUID of another version.
            The message names which, in the wording the validation library uses
            for its own errors, and never repeats the input.
    """
    if isinstance(value, str):
        try:
            value = UUID(value)
        except ValueError:
            raise ValueError("Input should be a valid UUID") from None
    if not isinstance(value, UUID):
        # A ValueError, not a TypeError: validation reports only the former as invalid input.
        raise ValueError("Input should be a valid UUID")  # noqa: TRY004
    if value.version != 7:  # noqa: PLR2004
        raise ValueError("Input should be a uuid7")
    return value
