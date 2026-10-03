"""Domain model: archives and the files in them.

An archive collects files under names that are unique within it, and has a name of its own.
This module holds the rules for those names. The format an archive is written in is not part
of the model.
"""

import unicodedata
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import PureWindowsPath
from typing import Annotated, Protocol, Self

from pydantic import (
    AfterValidator,
    ConfigDict,
    Field,
    PrivateAttr,
    SkipValidation,
    model_validator,
)

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


class Archive(Entity):
    """A collection of files to be packed together, each under a name of its own.

    No two files in an archive share a name, and names that differ only in letter case or
    Unicode form count as the same, as many file systems treat them. A file whose name is
    already taken is renamed when it is added, never dropped and never replacing another. Files
    keep the order in which they were added.
    """

    archive_id: Annotated[ArchiveID, Field(default_factory=ArchiveID.generate)]
    """The identity of the archive."""
    name: Annotated[ArchiveName, Field(default_factory=ArchiveName.generate)]
    """The name of the archive; generated from the time of creation unless one is given."""

    _entries: dict[str, ArchiveEntry] = PrivateAttr(default_factory=dict)
    """The entries, keyed by their folded names."""

    @property
    def identity(self) -> ArchiveID:
        return self.archive_id

    @property
    def entries(self) -> tuple[ArchiveEntry, ...]:
        """The files in the archive, in the order they were added."""
        return tuple(self._entries.values())

    def __contains__(self, name: object) -> bool:
        return isinstance(name, EntryName) and name.folded in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def add(self, name: EntryName, content: Content) -> ArchiveEntry:
        """Add a file under its name, or under a numbered form of the name if it is taken.

        The number is the smallest from 2 up that gives a free name, so a second `foo.txt`
        becomes `foo-2.txt`, and a third `foo-3.txt`.

        Args:
            name: The name the file should have.
            content: The bytes of the file.

        Returns:
            The entry as added. Its name differs from `name` if the file was renamed.
        """
        unique_name = name
        counter = 2
        while unique_name in self:
            unique_name = name.with_counter(counter)
            counter += 1
        entry = ArchiveEntry(name=unique_name, content=content)
        self._entries[unique_name.folded] = entry
        return entry


class ArchiveWriter(Protocol):
    """Writes an archive in one format, producing its bytes as they are ready."""

    media_type: str
    """The media type of the format, such as `application/zip`."""
    suffix: str
    """The file name suffix of the format, such as `.zip`."""

    def write(self, archive: Archive) -> AsyncIterator[bytes]:
        """Produce the archive's bytes, in order, reading each file's content as it goes."""
        ...
