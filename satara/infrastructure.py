"""Adapters for the ports declared in the domain."""

import asyncio
import zipfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from satara.domain import Archive

# How many bytes of a file are read, and compressed, at a time.
_CHUNK_SIZE = 64 * 1024


class _Buffer:
    """A write-only file-like object that holds what is written to it until it is taken.

    It meets `zipfile._ZipWritable`, the protocol the standard library's type stubs give for
    the file-like object a `ZipFile` writes to: `write`, `flush` and `close`. The protocol
    exists only in the stubs, so it cannot be named as a base class. Having no `seek`, the
    buffer makes `ZipFile` write each file's sizes after its data, never going back over bytes
    already taken.
    """

    def __init__(self) -> None:
        self._data = bytearray()

    def write(self, data: bytes) -> int:
        self._data += data
        return len(data)

    def flush(self) -> None:
        """Return without doing anything: the data stays here until it is taken."""

    def close(self) -> None:
        """Return without doing anything.

        `ZipFile` never closes a file-like object it was given.
        """

    def take(self) -> bytes:
        """Return everything written since the last call, and forget it."""
        data = bytes(self._data)
        self._data.clear()
        return data


class ZipArchiveWriter:
    """Writes an archive as a ZIP file, each file compressed with deflate.

    Every file is dated with the time, in UTC, the archive was written. Compression runs in a
    worker thread, one chunk at a time, so it does not hold up other requests. A file of about
    2 GiB or more is written with the ZIP64 extensions, which some older unzip tools cannot
    read.
    """

    media_type = "application/zip"
    suffix = ".zip"

    async def write(self, archive: Archive) -> AsyncIterator[bytes]:
        """Produce the archive's bytes, in order, reading each file's content as it goes."""
        buffer = _Buffer()
        written_at = datetime.now(UTC).timetuple()[:6]
        # The buffer cannot seek, so each file's sizes follow its data instead of preceding it.
        with zipfile.ZipFile(buffer, mode="w") as zip_file:
            for entry in archive.entries:
                info = zipfile.ZipInfo(str(entry.name), date_time=written_at)
                info.compress_type = zipfile.ZIP_DEFLATED
                # Told the size up front, the ZIP library uses ZIP64 for a file that needs it.
                info.file_size = entry.size
                with zip_file.open(info, mode="w") as file:
                    while chunk := await entry.content.read(_CHUNK_SIZE):
                        await asyncio.to_thread(file.write, chunk)
                        if data := buffer.take():
                            yield data
        if data := buffer.take():
            yield data
