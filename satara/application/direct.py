"""The direct flow: files sent in one request, packed into an archive returned at once."""

from collections.abc import AsyncIterator

from pydantic import ConfigDict, SkipValidation

from satara.application.base import (
    Command,
    Limits,
    Result,
    to_archive_name,
    to_entry_name,
)
from satara.common.models import FrozenModel
from satara.domain import Archive, ArchiveID, ArchiveWriter, Content


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

    def __init__(self, writer: ArchiveWriter, limits: Limits) -> None:
        """Set up the service.

        Args:
            writer: Writes archives in the format the service produces.
            limits: How much one archive may hold.
        """
        self._writer = writer
        self._limits = limits

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
        """
        self._limits.check(command.files)
        archive = (
            Archive()
            if command.archive_name is None
            else Archive(name=to_archive_name(command.archive_name))
        )
        for file in command.files:
            archive.add(to_entry_name(file.name), file.size, file.content)
        return ArchiveFilesResult(
            archive_id=archive.archive_id,
            file_name=f"{archive.name}{self._writer.suffix}",
            media_type=self._writer.media_type,
            chunks=self._writer.write(archive),
        )
