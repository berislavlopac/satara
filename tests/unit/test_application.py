import pytest

from satara.application import (
    ArchiveFilesCommand,
    ArchiveService,
    FileTooLargeError,
    InvalidFileNameError,
    NoFilesError,
    TooManyFilesError,
    UploadedFile,
)


@pytest.fixture
def service(recording_writer):
    return ArchiveService(recording_writer, max_files=3, max_file_size=10)


@pytest.fixture(scope="session")
def to_command(memory_content):
    def to_command(*files):
        return ArchiveFilesCommand(
            files=tuple(
                UploadedFile(name=name, size=len(data), content=memory_content(data))
                for name, data in files
            )
        )

    return to_command


def archived_names(recording_writer):
    (archive,) = recording_writer.archives
    return [str(entry.name) for entry in archive.entries]


def test_archive_files_refuses_an_empty_request(service, to_command):
    with pytest.raises(NoFilesError):
        service.archive_files(to_command())


def test_archive_files_refuses_more_files_than_the_limit(service, to_command):
    with pytest.raises(TooManyFilesError):
        service.archive_files(to_command(*[(f"{i}.txt", b"x") for i in range(4)]))


def test_archive_files_accepts_as_many_files_as_the_limit(
    service, to_command, recording_writer
):
    service.archive_files(to_command(*[(f"{i}.txt", b"x") for i in range(3)]))

    assert archived_names(recording_writer) == ["0.txt", "1.txt", "2.txt"]


def test_archive_files_refuses_a_file_larger_than_the_limit(service, to_command):
    with pytest.raises(FileTooLargeError):
        service.archive_files(to_command(("small.txt", b"x"), ("large.txt", b"x" * 11)))


def test_archive_files_accepts_a_file_as_large_as_the_limit(
    service, to_command, recording_writer
):
    service.archive_files(to_command(("exact.txt", b"x" * 10)))

    assert archived_names(recording_writer) == ["exact.txt"]


def test_archive_files_keeps_only_the_base_name_of_each_file(
    service, to_command, recording_writer
):
    service.archive_files(
        to_command(("dir/a.txt", b"a"), ("dir\\b.txt", b"b"), ("../../c.txt", b"c"))
    )

    assert archived_names(recording_writer) == ["a.txt", "b.txt", "c.txt"]


def test_archive_files_renames_files_whose_base_names_collide(
    service, to_command, recording_writer
):
    service.archive_files(to_command(("first/x.txt", b"1"), ("second/x.txt", b"2")))

    assert archived_names(recording_writer) == ["x.txt", "x-2.txt"]


@pytest.mark.parametrize(
    "name",
    ["", "..", "dir/..", "dir\\.."],
    ids=["empty", "parent directory", "slash", "backslash"],
)
def test_archive_files_refuses_a_file_without_a_usable_name(service, to_command, name):
    with pytest.raises(InvalidFileNameError):
        service.archive_files(to_command((name, b"x")))


async def test_archive_files_reads_no_content_until_the_archive_is_read(
    service, to_command, recording_writer
):
    result = service.archive_files(to_command(("a.txt", b"first"), ("b.txt", b"second")))
    (archive,) = recording_writer.archives
    contents = [entry.content for entry in archive.entries]

    assert [content.position for content in contents] == [0, 0]
    assert b"".join([chunk async for chunk in result.chunks]) == b"firstsecond"


def test_archive_files_takes_the_media_type_and_suffix_from_the_writer(
    service, to_command, recording_writer
):
    result = service.archive_files(to_command(("a.txt", b"a")))

    assert result.media_type == recording_writer.media_type
    assert result.file_name == f"{result.archive_id}{recording_writer.suffix}"
