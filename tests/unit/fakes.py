"""Test doubles, type-checked against the protocols they stand in for.

Tests receive these through fixtures and never import them.
"""

import asyncio
from collections.abc import AsyncIterator, Iterable

from satara.common.events import DomainEvent, DomainEventHandler, EventBroker
from satara.common.queue import MessageQueue, QueueMessage
from satara.domain import (
    Archive,
    ArchiveID,
    ArchiveNotFoundError,
    ArchiveRepository,
    ArchiveWriter,
    Content,
    FileStorage,
)


class MemoryContent(Content):
    """File content held in memory, recording how far it has been read."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.position = 0

    async def read(self, size: int = -1) -> bytes:
        end = len(self.data) if size < 0 else self.position + size
        chunk = self.data[self.position : end]
        self.position += len(chunk)
        return chunk


class RecordingWriter(ArchiveWriter):
    """An archive writer that keeps the last archive it was asked to write.

    It produces the content of each file in turn, with nothing around it.
    """

    media_type = "application/x-recorded"
    suffix = ".recorded"

    def __init__(self) -> None:
        self.archive: Archive | None = None

    def write(self, archive: Archive) -> AsyncIterator[bytes]:
        self.archive = archive
        return self._to_chunks(archive)

    async def _to_chunks(self, archive: Archive) -> AsyncIterator[bytes]:
        for entry in archive.entries:
            while chunk := await entry.content.read():
                yield chunk


class MemoryArchiveRepository(ArchiveRepository):
    """Keeps archives in memory, handing back the very objects it was given."""

    def __init__(self) -> None:
        self.archives: dict[ArchiveID, Archive] = {}

    async def add(self, archive: Archive) -> None:
        self.archives[archive.archive_id] = archive

    async def mark_failed(self, archive_id: ArchiveID) -> None:
        (await self.get(archive_id)).mark_failed()

    async def get(self, archive_id: ArchiveID) -> Archive:
        try:
            return self.archives[archive_id]
        except KeyError:
            raise ArchiveNotFoundError(str(archive_id)) from None


class StoredContent(Content):
    """A file's content in `MemoryFileStorage`, looked up only when first read."""

    def __init__(self, storage: MemoryFileStorage, key: tuple[ArchiveID, int]) -> None:
        self._storage = storage
        self._key = key
        self._content: MemoryContent | None = None

    async def read(self, size: int = -1) -> bytes:
        if self._content is None:
            self._content = MemoryContent(self._storage.files[self._key])
        return await self._content.read(size)


class MemoryFileStorage(FileStorage):
    """Holds files and archives in memory, and hands out URLs that say what they are for."""

    def __init__(self) -> None:
        self.files: dict[tuple[ArchiveID, int], bytes] = {}
        self.archives: dict[ArchiveID, tuple[str, bytes]] = {}

    async def create_upload_url(self, archive_id: ArchiveID, position: int, size: int) -> str:
        return f"upload://{archive_id}/{position}?size={size}"

    def open_file(self, archive_id: ArchiveID, position: int) -> Content:
        return StoredContent(self, (archive_id, position))

    async def save_archive(
        self, archive_id: ArchiveID, media_type: str, chunks: AsyncIterator[bytes]
    ) -> None:
        self.archives[archive_id] = (media_type, b"".join([chunk async for chunk in chunks]))

    async def create_download_url(self, archive_id: ArchiveID, file_name: str) -> str:
        return f"download://{archive_id}/{file_name}"


class RecordingBroker(EventBroker):
    """Records the events published, and delivers them to no one."""

    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    def subscribe[T: DomainEvent](
        self, event_type: type[T], handler: DomainEventHandler[T]
    ) -> None:
        pass

    async def publish(self, events: Iterable[DomainEvent]) -> None:
        self.published.extend(events)


class FailingBroker(EventBroker):
    """A broker whose every delivery fails, as when building an archive fails."""

    def subscribe[T: DomainEvent](
        self, event_type: type[T], handler: DomainEventHandler[T]
    ) -> None:
        pass

    async def publish(self, events: Iterable[DomainEvent]) -> None:
        if list(events):
            raise RuntimeError("The build failed")


class MemoryQueue(MessageQueue):
    """A queue that hands out prepared batches, then stops its consumer once they run out.

    It records the messages deleted, and leaves the rest as a real queue would.
    """

    def __init__(
        self, batches: list[list[QueueMessage]], stop: asyncio.Event, max_attempts: int | None
    ) -> None:
        self._batches = list(batches)
        self._stop = stop
        self._max_attempts = max_attempts
        self.deleted: list[QueueMessage] = []

    async def receive(self) -> list[QueueMessage]:
        if not self._batches:
            self._stop.set()
            return []
        return self._batches.pop(0)

    async def delete(self, message: QueueMessage) -> None:
        self.deleted.append(message)

    async def read_max_attempts(self) -> int | None:
        return self._max_attempts


class SampleEvent(DomainEvent):
    """An event for tests, labelled to tell one from another."""

    label: str
    """What tells this event apart."""


class OtherEvent(DomainEvent):
    """An event of another type than `SampleEvent`."""


class RecordingHandler(DomainEventHandler[SampleEvent]):
    """A handler that notes each event it handles, under its own name, in a shared log."""

    def __init__(self, name: str, log: list[tuple[str, str]]) -> None:
        self._name = name
        self._log = log

    async def handle(self, event: SampleEvent) -> None:
        self._log.append((self._name, event.label))


class FailingHandler(DomainEventHandler[SampleEvent]):
    """A handler that fails on every event."""

    async def handle(self, event: SampleEvent) -> None:
        raise RuntimeError("The handler failed")
