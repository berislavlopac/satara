import re

import pytest

from satara.application.base import (
    FileTooLargeError,
    InvalidArchiveNameError,
    InvalidFileNameError,
    Limits,
    NoFilesError,
    TooManyFilesError,
    TotalTooLargeError,
)
from satara.application.direct import ArchiveFilesCommand, ArchiveService, UploadedFile


@pytest.fixture
def service(recording_writer):
    return ArchiveService(
        recording_writer, Limits(max_files=3, max_file_size=10, max_total_size=25)
    )


@pytest.fixture(scope="session")
def build_archive_files_command(memory_content):
    def build_archive_files_command(*files, archive_name=None):
        return ArchiveFilesCommand(
            files=tuple(
                UploadedFile(name=name, size=len(data), content=memory_content(data))
                for name, data in files
            ),
            archive_name=archive_name,
        )

    return build_archive_files_command


def list_entry_names(archive):
    return [str(entry.name) for entry in archive.entries]


async def test_archive_files_turns_uploaded_files_into_a_named_archive(
    memory_content, recording_writer
):
    limits = Limits(max_files=3, max_file_size=10, max_total_size=100)
    service = ArchiveService(recording_writer, limits)
    command = ArchiveFilesCommand(
        files=(
            UploadedFile(name="notes.txt", size=5, content=memory_content(b"notes")),
            UploadedFile(name="data/table.csv", size=3, content=memory_content(b"1,2")),
        ),
        archive_name="report",
    )

    result = service.archive_files(command)
    data = b"".join([chunk async for chunk in result.chunks])

    assert result.file_name == "report.recorded"
    assert result.media_type == "application/x-recorded"
    assert data == b"notes1,2"


def test_archive_files_refuses_an_empty_request(service, build_archive_files_command):
    command = build_archive_files_command()

    with pytest.raises(NoFilesError):
        service.archive_files(command)


def test_archive_files_refuses_more_files_than_the_limit(service, build_archive_files_command):
    command = build_archive_files_command(*[(f"{i}.txt", b"x") for i in range(4)])

    with pytest.raises(TooManyFilesError):
        service.archive_files(command)


def test_archive_files_accepts_as_many_files_as_the_limit(
    service, build_archive_files_command, recording_writer
):
    command = build_archive_files_command(*[(f"{i}.txt", b"x") for i in range(3)])

    service.archive_files(command)

    assert list_entry_names(recording_writer.archive) == ["0.txt", "1.txt", "2.txt"]


def test_archive_files_refuses_a_file_larger_than_the_limit(
    service, build_archive_files_command
):
    command = build_archive_files_command(("small.txt", b"x"), ("large.txt", b"x" * 11))

    with pytest.raises(FileTooLargeError):
        service.archive_files(command)


def test_archive_files_accepts_a_file_as_large_as_the_limit(
    service, build_archive_files_command, recording_writer
):
    command = build_archive_files_command(("exact.txt", b"x" * 10))

    service.archive_files(command)

    assert list_entry_names(recording_writer.archive) == ["exact.txt"]


def test_archive_files_refuses_files_larger_together_than_the_limit(
    service, build_archive_files_command
):
    command = build_archive_files_command(*[(f"{i}.txt", b"x" * 9) for i in range(3)])

    with pytest.raises(TotalTooLargeError):
        service.archive_files(command)


def test_archive_files_keeps_only_the_base_name_of_each_file(
    service, build_archive_files_command, recording_writer
):
    command = build_archive_files_command(
        ("dir/a.txt", b"a"), ("dir\\b.txt", b"b"), ("../../c.txt", b"c")
    )

    service.archive_files(command)

    assert list_entry_names(recording_writer.archive) == ["a.txt", "b.txt", "c.txt"]


def test_archive_files_renames_files_whose_base_names_collide(
    service, build_archive_files_command, recording_writer
):
    command = build_archive_files_command(("first/x.txt", b"1"), ("second/x.txt", b"2"))

    service.archive_files(command)

    assert list_entry_names(recording_writer.archive) == ["x.txt", "x-2.txt"]


@pytest.mark.parametrize(
    "name",
    ["", "..", "dir/..", "dir\\..", "a\x00.txt"],
    ids=["empty", "parent directory", "slash", "backslash", "control character"],
)
def test_archive_files_refuses_a_file_without_a_usable_name(
    service, build_archive_files_command, name
):
    command = build_archive_files_command((name, b"x"))

    with pytest.raises(InvalidFileNameError):
        service.archive_files(command)


def test_archive_files_reads_no_content_until_the_archive_is_read(
    service, build_archive_files_command, recording_writer
):
    command = build_archive_files_command(("a.txt", b"first"), ("b.txt", b"second"))

    service.archive_files(command)

    contents = [entry.content for entry in recording_writer.archive.entries]
    assert [content.position for content in contents] == [0, 0]


def test_archive_files_takes_the_media_type_and_suffix_from_the_writer(
    service, build_archive_files_command, recording_writer
):
    command = build_archive_files_command(("a.txt", b"a"), archive_name="report")

    result = service.archive_files(command)

    assert result.media_type == recording_writer.media_type
    assert result.file_name == f"report{recording_writer.suffix}"


def test_archive_files_names_an_unnamed_archive_after_the_time_it_was_created(
    service, build_archive_files_command
):
    command = build_archive_files_command(("a.txt", b"a"))

    result = service.archive_files(command)

    assert re.fullmatch(r"archive-\d{8}T\d{6}Z\.recorded", result.file_name)


def test_archive_files_adds_the_suffix_even_to_a_name_ending_with_it(
    service, build_archive_files_command
):
    command = build_archive_files_command(("a.txt", b"a"), archive_name="report.recorded")

    result = service.archive_files(command)

    assert result.file_name == "report.recorded.recorded"


def test_archive_files_refuses_an_unusable_archive_name(service, build_archive_files_command):
    command = build_archive_files_command(("a.txt", b"a"), archive_name="../report")

    with pytest.raises(InvalidArchiveNameError):
        service.archive_files(command)
