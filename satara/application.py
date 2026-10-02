"""Use cases of the service."""

from collections.abc import AsyncIterator
from pathlib import PureWindowsPath

from pydantic import ConfigDict, SkipValidation, ValidationError

from satara.common.models import FrozenModel
from satara.domain import (
    Archive,
    ArchiveID,
    ArchiveName,
    ArchiveWriter,
    Content,
    EntryName,
)


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
    """A file's name leaves nothing usable once its directories are dropped."""


class InvalidArchiveNameError(UploadRejectedError):
    """The name requested for the archive breaks the rules for archive names."""


class UploadedFile(FrozenModel):
    """A file as the client sent it."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    """The name of the file as sent, possibly with directories."""
    size: int
    """The size of the file in bytes."""
    content: SkipValidation[Content]
    """The bytes of the file."""


class ArchiveFilesCommand(Command):
    """A request to pack files into one archive."""

    files: tuple[UploadedFile, ...]
    """The files, in the order they were sent."""
    archive_name: str | None = None
    """The name requested for the archive, without a suffix; generated if not given."""


class ArchiveFilesResult(Result):
    """An archive ready to be sent, with what is needed to describe it."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    archive_id: ArchiveID
    """The identity of the archive."""
    file_name: str
    """The name to offer for the archive: its name, with the format's suffix."""
    media_type: str
    """The media type of the archive's format."""
    chunks: SkipValidation[AsyncIterator[bytes]]
    """The bytes of the archive, produced only as they are read."""


class ArchiveService:
    """Packs uploaded files into an archive, within the configured limits."""

    def __init__(self, writer: ArchiveWriter, max_files: int, max_file_size: int) -> None:
        """Set up the service.

        Args:
            writer: Writes archives in the format the service produces.
            max_files: The most files one archive may hold.
            max_file_size: The largest size, in bytes, of a single file.
        """
        self._writer = writer
        self._max_files = max_files
        self._max_file_size = max_file_size

    def archive_files(self, command: ArchiveFilesCommand) -> ArchiveFilesResult:
        """Check the files against the limits and collect them into an archive.

        Each file keeps only the base name it was sent with. The format's suffix is added to the
        archive's name even when the name already ends with it. No content is read here: the
        archive's bytes are produced as the result's `chunks` are read, so every file has been
        accepted before the first byte.

        Args:
            command: The files to archive.

        Returns:
            The archive, described and ready to be read.

        Raises:
            NoFilesError: No files were sent.
            TooManyFilesError: More files were sent than the limit allows.
            FileTooLargeError: A file is larger than the limit allows.
            InvalidArchiveNameError: The requested archive name breaks the rules.
            InvalidFileNameError: A file's name leaves nothing usable.
        """
        files = command.files
        if not files:
            raise NoFilesError("No files were sent")
        if len(files) > self._max_files:
            raise TooManyFilesError(
                f"{len(files)} files were sent; at most {self._max_files} are allowed"
            )
        archive = (
            Archive()
            if command.archive_name is None
            else Archive(name=_to_archive_name(command.archive_name))
        )
        for file in files:
            # `PureWindowsPath` treats both `/` and `\` as separators, on any platform.
            base_name = PureWindowsPath(file.name).name
            if file.size > self._max_file_size:
                raise FileTooLargeError(
                    f"{base_name!r} is {file.size} bytes; "
                    f"at most {self._max_file_size} are allowed"
                )
            archive.add(_to_entry_name(base_name), file.content)
        return ArchiveFilesResult(
            archive_id=archive.archive_id,
            file_name=f"{archive.name}{self._writer.suffix}",
            media_type=self._writer.media_type,
            chunks=self._writer.write(archive),
        )


def _to_entry_name(base_name: str) -> EntryName:
    """Return the name a file takes in the archive.

    Raises:
        InvalidFileNameError: The base name is not a usable file name.
    """
    try:
        return EntryName.model_validate(base_name)
    except ValidationError:
        raise InvalidFileNameError(f"{base_name!r} is not a usable file name") from None


def _to_archive_name(name: str) -> ArchiveName:
    """Return the archive name requested.

    Raises:
        InvalidArchiveNameError: The name breaks the rules for archive names.
    """
    try:
        return ArchiveName.model_validate(name)
    except ValidationError:
        raise InvalidArchiveNameError(f"{name!r} is not a usable archive name") from None
