import os
import zipfile
from datetime import UTC, datetime, timedelta
from io import BytesIO

from hypothesis import given, strategies as st

from satara.domain import Archive, EntryName
from satara.infrastructure import ZipArchiveWriter


class MemoryContent:
    def __init__(self, data):
        self.data = data
        self.position = 0

    async def read(self, size=-1):
        end = len(self.data) if size < 0 else self.position + size
        chunk = self.data[self.position : end]
        self.position += len(chunk)
        return chunk


def to_archive(files):
    archive = Archive()
    for name, data in files:
        archive.add(EntryName.model_validate(name), MemoryContent(data))
    return archive


async def write(archive):
    return b"".join([chunk async for chunk in ZipArchiveWriter().write(archive)])


def read_back(data):
    with zipfile.ZipFile(BytesIO(data)) as zip_file:
        assert zip_file.testzip() is None
        return [(info.filename, zip_file.read(info)) for info in zip_file.infolist()]


file_names = st.text(
    alphabet=st.characters(categories=["L", "N"], include_characters=" .-_"),
    min_size=1,
).filter(lambda value: value not in {".", ".."})
files = st.lists(st.tuples(file_names, st.binary(max_size=1024)), max_size=10)


async def test_zip_archive_writer_keeps_names_content_and_order():
    added = [("b.txt", b"second " * 1000), ("a.bin", os.urandom(200_000)), ("empty", b"")]

    data = await write(to_archive(added))

    assert read_back(data) == added


async def test_zip_archive_writer_writes_an_empty_archive():
    assert read_back(await write(Archive())) == []


async def test_zip_archive_writer_keeps_a_name_outside_ascii():
    added = [("naïve résumé.txt", b"content")]

    assert read_back(await write(to_archive(added))) == added


async def test_zip_archive_writer_dates_each_file_with_the_time_it_was_written():
    before = datetime.now(UTC).replace(microsecond=0)
    data = await write(to_archive([("a.txt", b"a"), ("b.txt", b"b")]))
    after = datetime.now(UTC)

    with zipfile.ZipFile(BytesIO(data)) as zip_file:
        for info in zip_file.infolist():
            # The format stores seconds in steps of two.
            dated = datetime(*info.date_time, tzinfo=UTC)
            assert before - timedelta(seconds=2) <= dated <= after


async def test_zip_archive_writer_produces_bytes_before_a_file_is_fully_read():
    content = MemoryContent(os.urandom(1024 * 1024))
    archive = Archive()
    archive.add(EntryName.model_validate("large.bin"), content)
    chunks = ZipArchiveWriter().write(archive)

    await anext(chunks)

    assert 0 < content.position < len(content.data)
    await chunks.aclose()


@given(files)
async def test_zip_archive_writer_returns_every_file_as_it_was_added(added):
    archive = to_archive(added)
    expected = [
        (str(entry.name), data) for entry, (_, data) in zip(archive.entries, added, strict=True)
    ]

    assert read_back(await write(archive)) == expected
