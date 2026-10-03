import os
from datetime import timedelta
from http import HTTPStatus
from urllib.parse import urlsplit

import pytest
from aiobotocore.session import get_session

from satara.domain import Archive, EntryName
from satara.infrastructure.s3 import PART_SIZE, S3FileStorage

pytestmark = pytest.mark.integration


@pytest.fixture
async def archive(repository, storage):
    archive = Archive()
    for position, (name, size) in enumerate([("a.txt", 5), ("b.txt", 3)]):
        content = storage.open_file(archive.archive_id, position)
        archive.add(EntryName.model_validate(name), size, content)
    await repository.add(archive)
    return archive


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


async def test_storage_signs_each_URL_for_the_address_clients_reach_it_by(
    s3_client, client_options, settings, repository, archive, http
):
    """Signs with a client for `127.0.0.1`, while the storage itself talks to `localhost`."""
    options = client_options | {"endpoint_url": "http://127.0.0.1:4566"}
    async with get_session().create_client("s3", **options) as signing_client:
        storage = S3FileStorage(
            s3_client, settings.BUCKET, timedelta(minutes=5), signing_client=signing_client
        )

        url = await storage.create_upload_url(archive.archive_id, 0, 5)

    response = await http.put(url, content=b"hello")
    loaded = await repository.get(archive.archive_id)
    assert urlsplit(url).netloc == "127.0.0.1:4566"
    assert response.status_code == HTTPStatus.OK
    assert [str(entry.name) for entry in loaded.received] == ["a.txt"]
