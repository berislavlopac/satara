import os
from datetime import timedelta
from http import HTTPStatus
from urllib.parse import parse_qs, urlsplit

import pytest
from aiobotocore.session import get_session

from satara.domain import Archive, ArchiveID, ArchiveNotFoundError, ArchiveStatus, EntryName
from satara.infrastructure.s3 import PART_SIZE, S3FileStorage


@pytest.fixture
async def archive(s3_repository, s3_storage):
    archive = Archive(name="report")
    for position, (name, size) in enumerate([("a.txt", 5), ("b.txt", 3)]):
        content = s3_storage.open_file(archive.archive_id, position)
        archive.add(EntryName.model_validate(name), size, content)
    await s3_repository.add(archive)
    return archive


async def read_all(content):
    chunks = []
    while chunk := await content.read(64 * 1024):
        chunks.append(chunk)
    return b"".join(chunks)


async def test_repository_gives_back_a_new_archive_with_nothing_received(
    s3_repository, archive
):
    loaded = await s3_repository.get(archive.archive_id)

    files = [(str(entry.name), entry.size) for entry in loaded.entries]
    assert (loaded.name, files) == (archive.name, [("a.txt", 5), ("b.txt", 3)])
    assert (loaded.received, loaded.status) == ((), ArchiveStatus.PENDING)


async def test_repository_refuses_an_archive_it_does_not_hold(s3_repository):
    with pytest.raises(ArchiveNotFoundError):
        await s3_repository.get(ArchiveID.generate())


async def test_repository_marks_the_files_uploaded_as_received(
    s3_repository, s3_client, archive, bucket
):
    key = f"uploads/{archive.archive_id}/1"
    await s3_client.put_object(Bucket=bucket, Key=key, Body=b"abc")

    loaded = await s3_repository.get(archive.archive_id)

    assert [str(entry.name) for entry in loaded.received] == ["b.txt"]


async def test_repository_ignores_uploads_at_positions_no_file_has(
    s3_repository, s3_client, archive, bucket
):
    for position in ["2", "first", "0/extra"]:
        key = f"uploads/{archive.archive_id}/{position}"
        await s3_client.put_object(Bucket=bucket, Key=key, Body=b"x")

    loaded = await s3_repository.get(archive.archive_id)

    assert loaded.received == ()


async def test_repository_marks_an_archive_built_once_it_is_saved(
    s3_repository, s3_storage, archive
):
    async def chunks():
        yield b"zip"

    await s3_storage.save_archive(archive.archive_id, "application/zip", chunks())

    loaded = await s3_repository.get(archive.archive_id)
    assert loaded.status == ArchiveStatus.READY


async def test_repository_marks_an_archive_failed_once_told_so(s3_repository, archive):
    await s3_repository.mark_failed(archive.archive_id)

    loaded = await s3_repository.get(archive.archive_id)
    assert loaded.status == ArchiveStatus.FAILED


async def test_storage_reads_an_uploaded_file_back(s3_storage, s3_client, archive, bucket):
    key = f"uploads/{archive.archive_id}/0"
    await s3_client.put_object(Bucket=bucket, Key=key, Body=b"hello")

    data = await read_all(s3_storage.open_file(archive.archive_id, 0))

    assert data == b"hello"


async def test_storage_saves_an_archive_larger_than_one_part(
    s3_storage, s3_client, archive, bucket
):
    """Saves an archive of two parts, which comes back whole."""
    data = os.urandom(PART_SIZE + 1024)

    async def chunks():
        for start in range(0, len(data), 1024 * 1024):
            yield data[start : start + 1024 * 1024]

    await s3_storage.save_archive(archive.archive_id, "application/zip", chunks())

    key = f"archives/{archive.archive_id}/archive"
    stored = await s3_client.get_object(Bucket=bucket, Key=key)
    async with stored["Body"] as body:
        content = await body.read()
    assert (content, stored["ContentType"]) == (data, "application/zip")


async def test_storage_leaves_nothing_behind_when_an_archive_fails_to_save(
    s3_storage, s3_client, archive, bucket
):
    async def chunks():
        yield b"part of an archive"
        raise RuntimeError("The archive could not be written")

    with pytest.raises(RuntimeError):
        await s3_storage.save_archive(archive.archive_id, "application/zip", chunks())

    uploads = await s3_client.list_multipart_uploads(Bucket=bucket)
    objects = await s3_client.list_objects_v2(Bucket=bucket, Prefix="archives/")
    assert uploads.get("Uploads", []) == []
    assert [item["Key"] for item in objects["Contents"]] == [
        f"archives/{archive.archive_id}/manifest.json"
    ]


async def test_storage_signs_an_upload_URL_for_exactly_the_declared_size(
    s3_storage, archive, http, bucket
):
    url = await s3_storage.create_upload_url(archive.archive_id, 0, 5)

    response = await http.put(url, content=b"hello")

    query = parse_qs(urlsplit(url).query)
    assert response.status_code == HTTPStatus.OK
    assert urlsplit(url).path == f"/{bucket}/uploads/{archive.archive_id}/0"
    assert "content-length" in query["X-Amz-SignedHeaders"][0].split(";")
    assert query["X-Amz-Expires"] == ["300"]


async def test_storage_signs_a_download_URL_that_names_the_file(s3_storage, archive, bucket):
    url = await s3_storage.create_download_url(archive.archive_id, "report.zip")

    query = parse_qs(urlsplit(url).query)
    assert urlsplit(url).path == f"/{bucket}/archives/{archive.archive_id}/archive"
    assert query["response-content-disposition"] == ['attachment; filename="report.zip"']


async def test_storage_signs_each_URL_for_the_address_clients_reach_it_by(
    s3_client, client_options, archive, bucket
):
    options = client_options | {"endpoint_url": "http://storage.example:4566"}
    async with get_session().create_client("s3", **options) as signing_client:
        storage = S3FileStorage(
            s3_client, bucket, timedelta(minutes=5), signing_client=signing_client
        )

        url = await storage.create_upload_url(archive.archive_id, 0, 5)

    assert urlsplit(url).netloc == "storage.example:4566"
