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
from satara.application.deferred import (
    ArchiveBuilder,
    CheckUploadsCommand,
    CreateArchiveCommand,
    DeclaredFile,
    DeferredArchiveService,
    GetArchiveStatusCommand,
    RecordBuildFailureCommand,
)
from satara.domain import AllFilesReceived, ArchiveID, ArchiveNotFoundError, ArchiveStatus


@pytest.fixture
def service(repository, storage, broker, recording_writer):
    limits = Limits(max_files=3, max_file_size=10, max_total_size=25)
    return DeferredArchiveService(repository, storage, broker, recording_writer, limits)


def declare(*files, archive_name=None):
    return CreateArchiveCommand(
        files=tuple(DeclaredFile(name=name, size=size) for name, size in files),
        archive_name=archive_name,
    )


async def create_archive_of_two(service, repository):
    result = await service.create_archive(declare(("a.txt", 1), ("b.txt", 2)))
    return repository.archives[result.archive_id]


async def test_create_archive_gives_an_upload_URL_for_each_file_under_its_final_name(
    repository, storage, broker, recording_writer
):
    limits = Limits(max_files=3, max_file_size=10, max_total_size=25)
    service = DeferredArchiveService(repository, storage, broker, recording_writer, limits)
    command = CreateArchiveCommand(
        files=(
            DeclaredFile(name="notes.txt", size=5),
            DeclaredFile(name="old/notes.txt", size=7),
        ),
        archive_name="report",
    )

    result = await service.create_archive(command)

    archive_id = result.archive_id
    assert [(upload.name, upload.url) for upload in result.uploads] == [
        ("notes.txt", f"upload://{archive_id}/0?size=5"),
        ("notes-2.txt", f"upload://{archive_id}/1?size=7"),
    ]


async def test_create_archive_keeps_the_archive_with_its_declared_files(service, repository):
    command = declare(("a.txt", 1), ("b.txt", 2), archive_name="report")

    result = await service.create_archive(command)

    archive = repository.archives[result.archive_id]
    entries = [(str(entry.name), entry.size) for entry in archive.entries]
    assert (str(archive.name), entries) == ("report", [("a.txt", 1), ("b.txt", 2)])


@pytest.mark.parametrize(
    ("files", "archive_name", "error"),
    [
        ([], None, NoFilesError),
        ([("a", 1), ("b", 1), ("c", 1), ("d", 1)], None, TooManyFilesError),
        ([("a", 11)], None, FileTooLargeError),
        ([("a", 10), ("b", 10), ("c", 10)], None, TotalTooLargeError),
        ([("..", 1)], None, InvalidFileNameError),
        ([("a", 1)], "../report", InvalidArchiveNameError),
    ],
    ids=[
        "no files",
        "too many files",
        "a file too large",
        "too large together",
        "unusable file name",
        "unusable archive name",
    ],
)
async def test_create_archive_refuses_files_it_cannot_archive_and_keeps_nothing(
    service, repository, files, archive_name, error
):
    command = declare(*files, archive_name=archive_name)

    with pytest.raises(error):
        await service.create_archive(command)

    assert repository.archives == {}


async def test_get_archive_status_counts_the_files_received_while_pending(service, repository):
    archive = await create_archive_of_two(service, repository)
    archive.receive(archive.entries[0].name)
    command = GetArchiveStatusCommand(archive_id=archive.archive_id)

    result = await service.get_archive_status(command)

    assert (result.status, result.files_received, result.files_expected) == (
        ArchiveStatus.PENDING,
        1,
        2,
    )
    assert result.download_url is None


async def test_get_archive_status_gives_a_download_URL_once_ready(service, repository):
    archive = await create_archive_of_two(service, repository)
    archive.mark_built()
    command = GetArchiveStatusCommand(archive_id=archive.archive_id)

    result = await service.get_archive_status(command)

    assert result.status == ArchiveStatus.READY
    assert result.download_url == f"download://{archive.archive_id}/{archive.name}.recorded"


async def test_get_archive_status_refuses_an_unknown_archive(service):
    command = GetArchiveStatusCommand(archive_id=ArchiveID.generate())

    with pytest.raises(ArchiveNotFoundError):
        await service.get_archive_status(command)


async def test_check_uploads_publishes_that_all_files_arrived_once_they_have(
    service, repository, broker
):
    archive = await create_archive_of_two(service, repository)
    for entry in archive.entries:
        archive.receive(entry.name)

    await service.check_uploads(CheckUploadsCommand(archive_id=archive.archive_id))

    published = [(type(event), event.archive_id) for event in broker.published]
    assert published == [(AllFilesReceived, archive.archive_id)]


async def test_check_uploads_publishes_nothing_while_a_file_is_missing(
    service, repository, broker
):
    archive = await create_archive_of_two(service, repository)
    archive.receive(archive.entries[0].name)

    await service.check_uploads(CheckUploadsCommand(archive_id=archive.archive_id))

    assert broker.published == []


async def test_record_build_failure_marks_a_complete_archive_failed(service, repository):
    archive = await create_archive_of_two(service, repository)
    for entry in archive.entries:
        archive.receive(entry.name)

    await service.record_build_failure(RecordBuildFailureCommand(archive_id=archive.archive_id))

    assert archive.status == ArchiveStatus.FAILED


async def test_record_build_failure_leaves_an_incomplete_archive_pending(service, repository):
    """Leaves it pending, since a later upload can still complete it."""
    archive = await create_archive_of_two(service, repository)
    archive.receive(archive.entries[0].name)

    await service.record_build_failure(RecordBuildFailureCommand(archive_id=archive.archive_id))

    assert archive.status == ArchiveStatus.PENDING


async def test_archive_builder_stores_the_archive_written_from_the_uploaded_files(
    service, repository, storage, recording_writer
):
    archive = await create_archive_of_two(service, repository)
    storage.files[archive.archive_id, 0] = b"a"
    storage.files[archive.archive_id, 1] = b"bc"
    builder = ArchiveBuilder(repository, storage, recording_writer)

    await builder.handle(AllFilesReceived(archive_id=archive.archive_id))

    assert storage.archives[archive.archive_id] == ("application/x-recorded", b"abc")
