"""Domain model: archives and the files in them.

An archive collects files under names that are unique within it, and has a name of its own.
This module holds the rules for those names, and for when an archive whose files arrive after
it is created is complete. The format an archive is written in is not part of the model.
"""

import unicodedata
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PureWindowsPath
from typing import Annotated, Protocol, Self

from pydantic import (
    AfterValidator,
    ConfigDict,
    Field,
    NonNegativeInt,
    PrivateAttr,
    SkipValidation,
    model_validator,
)

from satara.common.events import DomainEvent
from satara.common.models import Entity, IDModel, ValueObject


class Content(Protocol):
    """The bytes of a file, read in chunks.

    Reading in chunks lets a file of any size pass through without being held in memory whole.
    """

    async def read(self, size: int = -1) -> bytes:
        """Read up to `size` bytes, or all remaining bytes if `size` is negative.

        Returns:
            The bytes read; empty once the content is exhausted.
        """
        ...


def _check_single_name(value: str) -> str:
    # `PureWindowsPath` treats both `/` and `\` as separators, and a leading `C:` as a drive.
    if value in {"", ".", ".."} or PureWindowsPath(value).name != value:
        raise ValueError("Input should be a single file name")
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise ValueError("Input should hold no control characters")
    return value


class EntryName(ValueObject):
    """The name a file has inside an archive.

    It is a single, non-empty file name, such as `report.pdf`, with no path, drive or control
    characters in it.
    """

    value: Annotated[str, AfterValidator(_check_single_name)]

    @model_validator(mode="before")
    @classmethod
    def _wrap_raw(cls, value: object) -> object:
        return {"value": value} if isinstance(value, str) else value

    def __str__(self) -> str:
        return self.value

    @property
    def folded(self) -> str:
        """The name as compared for a clash, ignoring letter case and Unicode form."""
        return unicodedata.normalize("NFD", unicodedata.normalize("NFD", self.value).casefold())

    def with_counter(self, counter: int) -> Self:
        """Return this name with a number added, to tell it apart from a name already taken.

        The number goes before the first dot, ignoring a dot at the start of the name:
        `foo.tar.gz` becomes `foo-2.tar.gz`, and `.bashrc` becomes `.bashrc-2`.

        Args:
            counter: The number to add.
        """
        extensions = "".join(PureWindowsPath(self.value).suffixes)
        stem = self.value.removesuffix(extensions)
        return self.model_validate(f"{stem}-{counter}{extensions}")


class ArchiveEntry(ValueObject):
    """A file as held in an archive: its content, under a name unique within that archive."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: EntryName
    """The name of the file in the archive."""
    size: NonNegativeInt
    """The size of the file in bytes."""
    content: SkipValidation[Content]
    """The bytes of the file."""


class ArchiveName(ValueObject):
    """The name of an archive, without the suffix of its format.

    It starts with an ASCII letter or digit and holds only ASCII letters, digits, `-`, `_` and
    `.`, up to 100 characters.
    """

    value: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$", max_length=100)]

    @model_validator(mode="before")
    @classmethod
    def _wrap_raw(cls, value: object) -> object:
        return {"value": value} if isinstance(value, str) else value

    def __str__(self) -> str:
        return self.value

    @classmethod
    def generate(cls) -> Self:
        """Generate a name from the current time in UTC, such as `archive-20261002T143015Z`."""
        return cls.model_validate(f"archive-{datetime.now(UTC):%Y%m%dT%H%M%SZ}")


class ArchiveID(IDModel):
    """The identity of an archive, assigned when the archive is created."""


class ArchiveStatus(StrEnum):
    """How far an archive has got."""

    PENDING = "pending"
    """Not built yet; files may still be arriving."""
    READY = "ready"
    """Built, and ready to be fetched."""


class AllFilesReceived(DomainEvent):
    """Every file an archive holds has arrived, so the archive can be built."""

    archive_id: ArchiveID
    """The archive whose files have all arrived."""


class Archive(Entity):
    """A collection of files to be packed together, each under a name of its own.

    No two files in an archive share a name, and names that differ only in letter case or
    Unicode form count as the same, as many file systems treat them. A file whose name is
    already taken is renamed when it is added, never dropped and never replacing another. Files
    keep the order in which they were added.

    A file's content may arrive after the file is added. Once every file has arrived, the
    archive can be built; after that it is ready.
    """

    archive_id: Annotated[ArchiveID, Field(default_factory=ArchiveID.generate)]
    """The identity of the archive."""
    name: Annotated[ArchiveName, Field(default_factory=ArchiveName.generate)]
    """The name of the archive; generated from the time of creation unless one is given."""

    _entries: dict[str, ArchiveEntry] = PrivateAttr(default_factory=dict)
    """The entries, keyed by their folded names."""
    _received: set[str] = PrivateAttr(default_factory=set)
    """The folded names of the entries whose content has arrived."""
    _is_built: bool = PrivateAttr(default=False)
    """Whether the archive has been built."""

    @property
    def identity(self) -> ArchiveID:
        return self.archive_id

    @property
    def entries(self) -> tuple[ArchiveEntry, ...]:
        """The files in the archive, in the order they were added."""
        return tuple(self._entries.values())

    @property
    def received(self) -> tuple[ArchiveEntry, ...]:
        """The files whose content has arrived, in the order they were added."""
        return tuple(entry for key, entry in self._entries.items() if key in self._received)

    @property
    def is_built(self) -> bool:
        """Whether the archive has been built."""
        return self._is_built

    @property
    def status(self) -> ArchiveStatus:
        """How far the archive has got."""
        return ArchiveStatus.READY if self._is_built else ArchiveStatus.PENDING

    def __contains__(self, name: object) -> bool:
        return isinstance(name, EntryName) and name.folded in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def add(self, name: EntryName, size: int, content: Content) -> ArchiveEntry:
        """Add a file under its name, or under a numbered form of the name if it is taken.

        The number is the smallest from 2 up that gives a free name, so a second `foo.txt`
        becomes `foo-2.txt`, and a third `foo-3.txt`.

        Args:
            name: The name the file should have.
            size: The size of the file in bytes.
            content: The bytes of the file.

        Returns:
            The entry as added. Its name differs from `name` if the file was renamed.
        """
        unique_name = name
        counter = 2
        while unique_name in self:
            unique_name = name.with_counter(counter)
            counter += 1
        entry = ArchiveEntry(name=unique_name, size=size, content=content)
        self._entries[unique_name.folded] = entry
        return entry

    def receive(self, name: EntryName) -> None:
        """Note that the content of the file under `name` has arrived.

        Raises:
            KeyError: The archive holds no file under `name`.
        """
        if name not in self:
            raise KeyError(f"The archive holds no file named {str(name)!r}")
        self._received.add(name.folded)

    def mark_built(self) -> None:
        """Note that the archive has been built."""
        self._is_built = True

    def check_complete(self) -> None:
        """Record `AllFilesReceived` if every file has arrived and the archive is not built.

        Each call checks afresh, so two calls on a complete archive record the event twice.
        """
        if not self._is_built and len(self._received) == len(self._entries):
            self.record_event(AllFilesReceived(archive_id=self.archive_id))


class ArchiveWriter(Protocol):
    """Writes an archive in one format, producing its bytes as they are ready."""

    media_type: str
    """The media type of the format, such as `application/zip`."""
    suffix: str
    """The file name suffix of the format, such as `.zip`."""

    def write(self, archive: Archive) -> AsyncIterator[bytes]:
        """Produce the archive's bytes, in order, reading each file's content as it goes."""
        ...


class ArchiveNotFoundError(LookupError):
    """No archive has the ID asked for."""


class ArchiveRepository(Protocol):
    """Keeps archives: their identity, name, files, and how far each has got.

    The content of the files is kept by `FileStorage`.
    """

    async def add(self, archive: Archive) -> None:
        """Keep a new archive."""
        ...

    async def get(self, archive_id: ArchiveID) -> Archive:
        """Return the archive with the given ID, as it stands now.

        Each file's content can be read once the file has arrived.

        Raises:
            ArchiveNotFoundError: No archive has the ID.
        """
        ...


class FileStorage(Protocol):
    """Holds the content of archived files, and each archive once it is built.

    A file is identified by its archive and its position in that archive, counting from 0.
    """

    async def create_upload_url(self, archive_id: ArchiveID, position: int, size: int) -> str:
        """Return a URL that accepts the file's content, of exactly `size` bytes, for a time."""
        ...

    def open_file(self, archive_id: ArchiveID, position: int) -> Content:
        """Return the file's content, read only as it is consumed."""
        ...

    async def save_archive(
        self, archive_id: ArchiveID, media_type: str, chunks: AsyncIterator[bytes]
    ) -> None:
        """Store the built archive's bytes, consuming them as they are produced."""
        ...

    async def create_download_url(self, archive_id: ArchiveID, file_name: str) -> str:
        """Return a URL that serves the built archive as `file_name`, for a time."""
        ...
