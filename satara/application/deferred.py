"""The deferred flow: files declared first, uploaded later, and archived once all arrive."""

from pydantic import NonNegativeInt

from satara.application.base import (
    Command,
    Limits,
    Result,
    to_archive_name,
    to_entry_name,
)
from satara.common.events import EventBroker
from satara.common.models import FrozenModel
from satara.domain import (
    Archive,
    ArchiveID,
    ArchiveRepository,
    ArchiveStatus,
    ArchiveWriter,
    FileStorage,
)


class DeclaredFile(FrozenModel):
    """A file as the client announces it, before uploading it."""

    name: str
    """The name of the file as sent, possibly with directories."""
    size: NonNegativeInt
    """The size of the file in bytes."""


class FileUpload(FrozenModel):
    """Where to upload one file."""

    name: str
    """The name the file has in the archive."""
    url: str
    """The URL that accepts the file's content."""


class CreateArchiveCommand(Command):
    """A request to create an archive whose files are uploaded afterwards."""

    files: tuple[DeclaredFile, ...]
    """The files, in the order they are to appear in the archive."""
    archive_name: str | None = None
    """The name requested for the archive, without a suffix; generated if not given."""


class CreateArchiveResult(Result):
    """An archive waiting for its files, with where to upload each."""

    archive_id: ArchiveID
    """The identity of the archive."""
    uploads: tuple[FileUpload, ...]
    """Where to upload each file, in the order the files were declared."""


class GetArchiveStatusCommand(Command):
    """A request for how far an archive has got."""

    archive_id: ArchiveID
    """The identity of the archive."""


class GetArchiveStatusResult(Result):
    """How far an archive has got."""

    archive_id: ArchiveID
    """The identity of the archive."""
    status: ArchiveStatus
    """Whether the archive is still pending or ready."""
    files_received: int
    """How many of the archive's files have arrived."""
    files_expected: int
    """How many files the archive holds."""
    download_url: str | None = None
    """Where to download the archive once it is ready."""


class CheckUploadsCommand(Command):
    """A request to check whether all of an archive's files have arrived."""

    archive_id: ArchiveID
    """The identity of the archive."""


class DeferredArchiveService:
    """Creates archives whose files are uploaded to storage, and tracks them until built."""

    def __init__(
        self,
        repository: ArchiveRepository,
        storage: FileStorage,
        broker: EventBroker,
        writer: ArchiveWriter,
        limits: Limits,
    ) -> None:
        """Set up the service.

        Args:
            repository: Keeps the archives.
            storage: Holds the files' content and the built archives.
            broker: Delivers the events the archives record.
            writer: The format archives are built in, which names their files.
            limits: How much one archive may hold.
        """
        self._repository = repository
        self._storage = storage
        self._broker = broker
        self._writer = writer
        self._limits = limits

    async def create_archive(self, command: CreateArchiveCommand) -> CreateArchiveResult:
        """Check the declared files, keep the archive, and give a URL to upload each file to.

        The files are named as in the direct flow: each keeps only its base name, renamed if
        the name is taken. Each URL accepts only a file of the declared size.

        Args:
            command: The archive's name and its files.

        Returns:
            The new archive's identity, and where to upload each file.
        """
        self._limits.check(command.files)
        archive = (
            Archive()
            if command.archive_name is None
            else Archive(name=to_archive_name(command.archive_name))
        )
        for position, file in enumerate(command.files):
            content = self._storage.open_file(archive.archive_id, position)
            archive.add(to_entry_name(file.name), file.size, content)
        await self._repository.add(archive)
        uploads = [
            FileUpload(
                name=str(entry.name),
                url=await self._storage.create_upload_url(
                    archive.archive_id, position, entry.size
                ),
            )
            for position, entry in enumerate(archive.entries)
        ]
        return CreateArchiveResult(archive_id=archive.archive_id, uploads=tuple(uploads))

    async def get_archive_status(
        self, command: GetArchiveStatusCommand
    ) -> GetArchiveStatusResult:
        """Report how far an archive has got, with a download URL once it is ready.

        Args:
            command: The archive to report on.

        Returns:
            The archive's status and how many of its files have arrived.
        """
        archive = await self._repository.get(command.archive_id)
        download_url = None
        if archive.is_built:
            file_name = f"{archive.name}{self._writer.suffix}"
            download_url = await self._storage.create_download_url(
                archive.archive_id, file_name
            )
        return GetArchiveStatusResult(
            archive_id=archive.archive_id,
            status=archive.status,
            files_received=len(archive.received),
            files_expected=len(archive),
            download_url=download_url,
        )

    async def check_uploads(self, command: CheckUploadsCommand) -> None:
        """Check whether all of an archive's files have arrived, and publish what that shows.

        Args:
            command: The archive to check.
        """
        archive = await self._repository.get(command.archive_id)
        archive.check_complete()
        await self._broker.publish(archive.pull_events())
