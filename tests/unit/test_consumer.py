import asyncio
import json

import pytest

from satara.application.base import Limits
from satara.application.deferred import DeferredArchiveService
from satara.common.queue import QueueMessage
from satara.domain import AllFilesReceived, Archive, ArchiveID, ArchiveStatus, EntryName
from satara.presentation.consumer import Consumer, to_archive_id


def build_notification(key):
    record = {"eventName": "ObjectCreated:Put", "s3": {"object": {"key": key, "size": 5}}}
    return QueueMessage(body=json.dumps({"Records": [record]}), handle="h", attempt=1)


def test_to_archive_ID_reads_the_archive_from_an_upload_notification():
    archive_id = ArchiveID.generate()
    message = build_notification(f"uploads%2F{archive_id}%2F3")

    result = to_archive_id(message)

    assert result == archive_id


@pytest.mark.parametrize(
    "message",
    [
        QueueMessage(body=json.dumps({"Event": "s3:TestEvent"}), handle="h", attempt=1),
        build_notification(f"archives/{ArchiveID.generate()}/archive"),
        build_notification("uploads/not-an-id/0"),
        QueueMessage(body="not JSON", handle="h", attempt=1),
        QueueMessage(body=json.dumps({"Records": ["not an event"]}), handle="h", attempt=1),
    ],
    ids=["test event", "not an upload", "no archive ID", "not JSON", "not an event"],
)
def test_to_archive_ID_ignores_anything_but_an_upload_notification(message):
    result = to_archive_id(message)

    assert result is None


@pytest.fixture
def build_consumer(repository, storage, recording_writer, memory_queue):
    """Build a consumer over prepared batches, with a broker of the test's choice."""

    def build_consumer(broker, *batches):
        limits = Limits(max_files=10, max_file_size=100, max_total_size=1000)
        service = DeferredArchiveService(repository, storage, broker, recording_writer, limits)
        stop = asyncio.Event()
        queue = memory_queue(list(batches), stop, max_attempts=3)
        return Consumer(queue, service), queue, stop

    return build_consumer


@pytest.fixture
def store_archive(repository, storage):
    """Store an archive of two files, both arrived if `complete`, the first only if not."""

    async def store_archive(complete):
        archive = Archive()
        for position, name in enumerate(["a.txt", "b.txt"]):
            content = storage.open_file(archive.archive_id, position)
            archive.add(EntryName.model_validate(name), 1, content)
        await repository.add(archive)
        for entry in archive.entries if complete else archive.entries[:1]:
            archive.receive(entry.name)
        return archive

    return store_archive


def build_upload_message(archive, position=0, attempt=1):
    message = build_notification(f"uploads/{archive.archive_id}/{position}")
    return message.model_copy(update={"attempt": attempt})


async def test_consumer_checks_an_archive_once_for_all_its_messages(
    build_consumer, store_archive, broker
):
    archive = await store_archive(complete=True)
    messages = [build_upload_message(archive, 0), build_upload_message(archive, 1)]
    consumer, queue, stop = build_consumer(broker, messages)

    await consumer.run(stop)

    assert [type(event) for event in broker.published] == [AllFilesReceived]
    assert queue.deleted == messages


async def test_consumer_deletes_a_message_that_is_not_an_upload(build_consumer, broker):
    body = json.dumps({"Event": "s3:TestEvent"})
    message = QueueMessage(body=body, handle="h", attempt=1)
    consumer, queue, stop = build_consumer(broker, [message])

    await consumer.run(stop)

    assert queue.deleted == [message]


async def test_consumer_deletes_the_messages_of_an_archive_that_does_not_exist(
    build_consumer, broker
):
    message = build_upload_message(Archive())
    consumer, queue, stop = build_consumer(broker, [message])

    await consumer.run(stop)

    assert queue.deleted == [message]


async def test_consumer_keeps_the_messages_of_a_failed_check_for_another_attempt(
    build_consumer, store_archive, failing_broker
):
    archive = await store_archive(complete=True)
    consumer, queue, stop = build_consumer(
        failing_broker, [build_upload_message(archive, attempt=1)]
    )

    await consumer.run(stop)

    assert queue.deleted == []
    assert archive.status == ArchiveStatus.PENDING


async def test_consumer_records_a_failed_build_on_the_last_attempt(
    build_consumer, store_archive, failing_broker
):
    archive = await store_archive(complete=True)
    consumer, queue, stop = build_consumer(
        failing_broker, [build_upload_message(archive, attempt=3)]
    )

    await consumer.run(stop)

    assert queue.deleted == []
    assert archive.status == ArchiveStatus.FAILED
