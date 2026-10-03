import os
import zipfile
from contextlib import aclosing
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from satara.domain import Archive, EntryName
from satara.infrastructure import ZipArchiveWriter


@pytest.fixture(scope="session")
def build_archive(memory_content):
    def build_archive(files):
        archive = Archive()
        for name, data in files:
            archive.add(EntryName.model_validate(name), len(data), memory_content(data))
        return archive

    return build_archive


def read_back(data):
    """Return the name and content of each file in a ZIP archive, in order.

    Reading a file checks its CRC, so a damaged archive raises rather than returning.
    """
    with zipfile.ZipFile(BytesIO(data)) as zip_file:
        return [(info.filename, zip_file.read(info)) for info in zip_file.infolist()]


file_names = st.text(
    alphabet=st.characters(categories=["L", "N"], include_characters=" .-_"),
    min_size=1,
).filter(lambda value: value not in {".", ".."})
files = st.lists(st.tuples(file_names, st.binary(max_size=1024)), max_size=10)


def is_entry_name(value):
    try:
        EntryName.model_validate(value)
    except ValidationError:
        return False
    return True


async def test_zip_archive_writer_keeps_names_content_and_order(build_archive):
    added = [("b.txt", b"second " * 1000), ("a.bin", os.urandom(200_000)), ("empty", b"")]
    archive = build_archive(added)

    data = b"".join([chunk async for chunk in ZipArchiveWriter().write(archive)])

    assert read_back(data) == added


async def test_zip_archive_writer_writes_an_empty_archive():
    archive = Archive()

    data = b"".join([chunk async for chunk in ZipArchiveWriter().write(archive)])

    assert read_back(data) == []


async def test_zip_archive_writer_keeps_a_name_outside_ascii(build_archive):
    archive = build_archive([("naïve résumé.txt", b"content")])

    data = b"".join([chunk async for chunk in ZipArchiveWriter().write(archive)])

    assert read_back(data) == [("naïve résumé.txt", b"content")]


async def test_zip_archive_writer_dates_files_with_the_time_the_archive_was_written(
    build_archive,
):
    archive = build_archive([("a.txt", b"a")])
    before = datetime.now(UTC).replace(microsecond=0)

    data = b"".join([chunk async for chunk in ZipArchiveWriter().write(archive)])

    after = datetime.now(UTC)
    with zipfile.ZipFile(BytesIO(data)) as zip_file:
        dated = datetime(*zip_file.getinfo("a.txt").date_time, tzinfo=UTC)
    # The format stores seconds in steps of two, rounding down.
    assert before - timedelta(seconds=2) <= dated <= after


async def test_zip_archive_writer_produces_bytes_before_a_file_is_fully_read(memory_content):
    content = memory_content(os.urandom(1024 * 1024))
    archive = Archive()
    archive.add(EntryName.model_validate("large.bin"), len(content.data), content)

    async with aclosing(ZipArchiveWriter().write(archive)) as chunks:
        await anext(chunks)

    assert 0 < content.position < len(content.data)


@given(files)
async def test_zip_archive_writer_returns_every_file_as_it_was_added(build_archive, added):
    archive = build_archive(added)
    expected = [
        (str(entry.name), data) for entry, (_, data) in zip(archive.entries, added, strict=True)
    ]

    data = b"".join([chunk async for chunk in ZipArchiveWriter().write(archive)])

    assert read_back(data) == expected


@given(st.text().filter(is_entry_name))
async def test_zip_archive_writer_keeps_any_name_an_entry_may_have(build_archive, name):
    """Writes every name the domain accepts exactly as it is.

    The text is drawn from all of Unicode, so a character the format would alter or drop is
    found here rather than in an extracted archive.
    """
    archive = build_archive([(name, b"")])

    data = b"".join([chunk async for chunk in ZipArchiveWriter().write(archive)])

    assert read_back(data) == [(name, b"")]
