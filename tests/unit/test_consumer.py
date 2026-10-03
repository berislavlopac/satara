import json

import pytest

from satara.domain import ArchiveID
from satara.presentation.consumer import to_archive_id


def notification(key):
    record = {"eventName": "ObjectCreated:Put", "s3": {"object": {"key": key, "size": 5}}}
    return {"Body": json.dumps({"Records": [record]}), "ReceiptHandle": "handle"}


def test_to_archive_ID_reads_the_archive_from_an_upload_notification():
    archive_id = ArchiveID.generate()
    message = notification(f"uploads%2F{archive_id}%2F3")

    result = to_archive_id(message)

    assert result == archive_id


@pytest.mark.parametrize(
    "message",
    [
        {"Body": json.dumps({"Event": "s3:TestEvent"}), "ReceiptHandle": "handle"},
        notification(f"archives/{ArchiveID.generate()}/archive"),
        notification("uploads/not-an-id/0"),
        {"Body": "not JSON", "ReceiptHandle": "handle"},
    ],
    ids=["test event", "not an upload", "no archive ID", "not JSON"],
)
def test_to_archive_ID_ignores_anything_but_an_upload_notification(message):
    result = to_archive_id(message)

    assert result is None
