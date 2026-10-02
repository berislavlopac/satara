"""Test doubles, type-checked against the protocols they stand in for.

Tests receive these through fixtures and never import them.
"""

from collections.abc import AsyncIterator

from satara.domain import Archive, ArchiveWriter, Content


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
