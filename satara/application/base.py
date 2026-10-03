"""What the use cases share: their base classes, the reasons they refuse, and name checks."""

from collections.abc import Sequence
from pathlib import PureWindowsPath
from typing import Protocol

from pydantic import ValidationError

from satara.common.models import FrozenModel
from satara.domain import ArchiveName, EntryName


class Command(FrozenModel):
    """Base class for the input to a use case."""


class Result(FrozenModel):
    """Base class for the output of a use case."""


class UploadRejectedError(Exception):
    """Base class for the reasons a set of files cannot be archived."""


class NoFilesError(UploadRejectedError):
    """No files were sent."""


class TooManyFilesError(UploadRejectedError):
    """More files were sent than the limit allows."""


class FileTooLargeError(UploadRejectedError):
    """A file is larger than the limit allows."""


class TotalTooLargeError(UploadRejectedError):
    """The files together are larger than the limit allows."""


class InvalidFileNameError(UploadRejectedError):
    """A file's name is not a usable file name once its directories are dropped."""


class InvalidArchiveNameError(UploadRejectedError):
    """The name requested for the archive breaks the rules for archive names."""


class SentFile(Protocol):
    """A file as the client describes it: its name as sent, and its size."""

    @property
    def name(self) -> str: ...

    @property
    def size(self) -> int: ...


class Limits(FrozenModel):
    """How much one archive may hold."""

    max_files: int
    """The most files."""
    max_file_size: int
    """The largest size of a single file, in bytes."""
    max_total_size: int
    """The largest size of all the files together, in bytes."""

    def check(self, files: Sequence[SentFile]) -> None:
        """Check that the files are within the limits.

        Raises:
            NoFilesError: There are no files.
            TooManyFilesError: There are more files than the limit allows.
            FileTooLargeError: A file is larger than the limit allows.
            TotalTooLargeError: The files together are larger than the limit allows.
        """
        if not files:
            raise NoFilesError("No files were sent")
        if len(files) > self.max_files:
            raise TooManyFilesError(
                f"{len(files)} files were sent; at most {self.max_files} are allowed"
            )
        for file in files:
            if file.size > self.max_file_size:
                raise FileTooLargeError(
                    f"{file.name!r} is {file.size} bytes; "
                    f"at most {self.max_file_size} are allowed"
                )
        total = sum(file.size for file in files)
        if total > self.max_total_size:
            raise TotalTooLargeError(
                f"The files total {total} bytes; at most {self.max_total_size} are allowed"
            )


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
