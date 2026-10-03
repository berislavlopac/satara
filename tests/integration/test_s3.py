import asyncio
import json
import os
from http import HTTPStatus

import pytest

from satara.domain import Archive, ArchiveID, ArchiveNotFoundError, EntryName
from satara.infrastructure.s3 import PART_SIZE

pytestmark = pytest.mark.integration


@pytest.fixture
async def archive(repository, storage):
    archive = Archive()
    for position, (name, size) in enumerate([("a.txt", 5), ("b.txt", 3)]):
        content = storage.open_file(archive.archive_id, position)
        archive.add(EntryName.model_validate(name), size, content)
    await repository.add(archive)
    return archive


async def read_all(content):
    chunks = []
    while chunk := await content.read(64 * 1024):
        chunks.append(chunk)
    return b"".join(chunks)


async def test_repository_gives_back_a_new_archive_with_nothing_received(repository, archive):
    loaded = await repository.get(archive.archive_id)

    files = [(str(entry.name), entry.size) for entry in loaded.entries]
    assert (loaded.name, files) == (archive.name, [("a.txt", 5), ("b.txt", 3)])
    assert (loaded.received, loaded.is_built) == ((), False)


async def test_repository_refuses_an_archive_it_does_not_hold(repository):
    with pytest.raises(ArchiveNotFoundError):
        await repository.get(ArchiveID.generate())


async def test_an_upload_through_its_URL_marks_the_file_received(
    repository, storage, archive, http
):
    url = await storage.create_upload_url(archive.archive_id, 0, 5)

    response = await http.put(url, content=b"hello")

    loaded = await repository.get(archive.archive_id)
    assert response.status_code == HTTPStatus.OK
    assert [str(entry.name) for entry in loaded.received] == ["a.txt"]


async def test_storage_refuses_an_upload_of_another_size(repository, storage, archive, http):
    url = await storage.create_upload_url(archive.archive_id, 0, 5)

    response = await http.put(url, content=b"hello world")

    loaded = await repository.get(archive.archive_id)
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert loaded.received == ()


async def test_an_uploaded_file_reads_back_from_storage(storage, archive, http):
    url = await storage.create_upload_url(archive.archive_id, 1, 3)
    await http.put(url, content=b"abc")

    data = await read_all(storage.open_file(archive.archive_id, 1))

    assert data == b"abc"


async def test_a_saved_archive_downloads_under_its_file_name(storage, archive, http):
    """Saves an archive larger than one part, so the upload has more than one."""
    data = os.urandom(PART_SIZE + 1024)

    async def chunks():
        for start in range(0, len(data), 1024 * 1024):
            yield data[start : start + 1024 * 1024]

    await storage.save_archive(archive.archive_id, "application/zip", chunks())

    url = await storage.create_download_url(archive.archive_id, "report.zip")
    response = await http.get(url)
    assert response.content == data
    assert response.headers["content-disposition"] == 'attachment; filename="report.zip"'


async def test_repository_marks_an_archive_built_once_it_is_saved(repository, storage, archive):
    async def chunks():
        yield b"zip"

    await storage.save_archive(archive.archive_id, "application/zip", chunks())

    loaded = await repository.get(archive.archive_id)
    assert loaded.is_built


async def test_an_upload_notifies_the_queue(storage, archive, http, sqs_client, settings):
    """Sends an upload and looks for its notification among the messages waiting.

    Other tests' uploads notify the same queue, so their messages are read and deleted too.
    """
    queue_url = (await sqs_client.get_queue_url(QueueName=settings.QUEUE))["QueueUrl"]
    key = f"uploads/{archive.archive_id}/0"
    url = await storage.create_upload_url(archive.archive_id, 0, 5)

    await http.put(url, content=b"hello")

    events = []
    async with asyncio.timeout(10):
        while key not in [event["s3"]["object"]["key"] for event in events]:
            response = await sqs_client.receive_message(
                QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=1
            )
            for message in response.get("Messages", []):
                events.extend(json.loads(message["Body"]).get("Records", []))
                await sqs_client.delete_message(
                    QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
                )
    names = {event["eventName"] for event in events if event["s3"]["object"]["key"] == key}
    assert names == {"ObjectCreated:Put"}
