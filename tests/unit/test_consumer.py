import json

import pytest

from satara.common.queue import QueueMessage
from satara.domain import ArchiveID
from satara.presentation.consumer import to_archive_id


def notification(key):
    record = {"eventName": "ObjectCreated:Put", "s3": {"object": {"key": key, "size": 5}}}
    return QueueMessage(body=json.dumps({"Records": [record]}), receipt="r", receive_count=1)


def test_to_archive_ID_reads_the_archive_from_an_upload_notification():
    archive_id = ArchiveID.generate()
    message = notification(f"uploads%2F{archive_id}%2F3")

    result = to_archive_id(message)

    assert result == archive_id


@pytest.mark.parametrize(
    "message",
    [
        QueueMessage(body=json.dumps({"Event": "s3:TestEvent"}), receipt="r", receive_count=1),
        notification(f"archives/{ArchiveID.generate()}/archive"),
        notification("uploads/not-an-id/0"),
        QueueMessage(body="not JSON", receipt="r", receive_count=1),
    ],
    ids=["test event", "not an upload", "no archive ID", "not JSON"],
)
def test_to_archive_ID_ignores_anything_but_an_upload_notification(message):
    result = to_archive_id(message)

    assert result is None
