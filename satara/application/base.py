"""What the use cases share: their base classes, the reasons they refuse, and name checks."""

from pathlib import PureWindowsPath

from pydantic import ValidationError

from satara.common.models import FrozenModel
from satara.domain import ArchiveName, EntryName


class Command(FrozenModel):
    """Base class for the input to a use case."""


class Result(FrozenModel):
    """Base class for the output of a use case."""


class UploadRejectedError(Exception):
    """Base class for the reasons a set of uploaded files cannot be archived."""


class NoFilesError(UploadRejectedError):
    """No files were sent."""


class TooManyFilesError(UploadRejectedError):
    """More files were sent than the limit allows."""


class FileTooLargeError(UploadRejectedError):
    """A file is larger than the limit allows."""


class InvalidFileNameError(UploadRejectedError):
    """A file's name is not a usable file name once its directories are dropped."""


class InvalidArchiveNameError(UploadRejectedError):
    """The name requested for the archive breaks the rules for archive names."""


def to_entry_name(sent_name: str) -> EntryName:
    """Return the name a file takes in the archive: its base name.

    Raises:
        InvalidFileNameError: The base name is not a usable file name.
    """
    # `PureWindowsPath` treats both `/` and `\` as separators, on any platform.
    base_name = PureWindowsPath(sent_name).name
    try:
        return EntryName.model_validate(base_name)
    except ValidationError:
        raise InvalidFileNameError(f"{sent_name!r} is not a usable file name") from None


def to_archive_name(name: str) -> ArchiveName:
    """Return the archive name requested.

    Raises:
        InvalidArchiveNameError: The name breaks the rules for archive names.
    """
    try:
        return ArchiveName.model_validate(name)
    except ValidationError:
        raise InvalidArchiveNameError(f"{name!r} is not a usable archive name") from None
