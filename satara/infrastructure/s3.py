"""Archives and their files kept in an S3 bucket.

Each archive has two prefixes. `uploads/<id>/<n>` holds the file at position `n`, uploaded by
the client; the bucket notifies of objects under `uploads/` only. `archives/<id>/` holds the
manifest, written once when the archive is created, and the built archive.
"""

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import TYPE_CHECKING

from aiobotocore.response import StreamingBody

from satara.common.models import FrozenModel
from satara.domain import (
    Archive,
    ArchiveID,
    ArchiveName,
    ArchiveNotFoundError,
    Content,
    EntryName,
    FileStorage,
)

if TYPE_CHECKING:
    from types_aiobotocore_s3 import S3Client
    from types_aiobotocore_s3.type_defs import CompletedPartTypeDef

PART_SIZE = 16 * 2**20
"""The size of each part of a built archive's upload but the last.

S3 takes at most 10,000 parts, so this bounds a built archive at about 156 GiB.
"""

_ARCHIVE = "archive"
_MANIFEST = "manifest.json"


def _to_upload_prefix(archive_id: ArchiveID) -> str:
    return f"uploads/{archive_id}/"


def _to_archive_prefix(archive_id: ArchiveID) -> str:
    return f"archives/{archive_id}/"


class S3Content:
    """A stored file's content, fetched only when first read."""

    def __init__(self, client: S3Client, bucket: str, key: str) -> None:
        self._client = client
        self._bucket = bucket
        self._key = key
        self._body: StreamingBody | None = None

    async def read(self, size: int = -1) -> bytes:
        """Read up to `size` bytes, or all remaining bytes if `size` is negative.

        Returns:
            The bytes read; empty once the content is exhausted.
        """
        if self._body is None:
            response = await self._client.get_object(Bucket=self._bucket, Key=self._key)
            self._body = response["Body"]
        chunk = await self._body.read(size if size >= 0 else None)
        if not chunk:
            self._body.close()
        return chunk


class S3FileStorage:
    """Keeps files and built archives in a bucket, handing out presigned URLs for them."""

    def __init__(
        self,
        client: S3Client,
        bucket: str,
        url_lifetime: timedelta,
        signing_client: S3Client | None = None,
    ) -> None:
        """Set up the storage.

        Args:
            client: The S3 client, open for as long as the storage is used.
            bucket: The bucket that holds the archives.
            url_lifetime: How long a presigned URL stays valid.
            signing_client: A client for the address clients reach storage by, to sign URLs
                with, if it differs from `client`'s. Signing makes no request.
        """
        self._client = client
        self._signing_client = signing_client or client
        self._bucket = bucket
        self._expires_in = int(url_lifetime.total_seconds())

    async def create_upload_url(self, archive_id: ArchiveID, position: int, size: int) -> str:
        """Return a presigned URL that accepts a PUT of exactly `size` bytes."""
        return await self._signing_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": f"{_to_upload_prefix(archive_id)}{position}",
                "ContentLength": size,
            },
            ExpiresIn=self._expires_in,
        )

    def open_file(self, archive_id: ArchiveID, position: int) -> Content:
        """Return the uploaded file's content, fetched only when first read."""
        key = f"{_to_upload_prefix(archive_id)}{position}"
        return S3Content(self._client, self._bucket, key)

    async def save_archive(
        self, archive_id: ArchiveID, media_type: str, chunks: AsyncIterator[bytes]
    ) -> None:
        """Store the built archive with a multipart upload, a part at a time.

        The upload is aborted if producing or sending the bytes fails, so no part is left
        behind.
        """
        key = f"{_to_archive_prefix(archive_id)}{_ARCHIVE}"
        upload = await self._client.create_multipart_upload(
            Bucket=self._bucket, Key=key, ContentType=media_type
        )
        upload_id = upload["UploadId"]
        parts: list[CompletedPartTypeDef] = []

        async def send(data: bytes) -> None:
            number = len(parts) + 1
            response = await self._client.upload_part(
                Bucket=self._bucket, Key=key, UploadId=upload_id, PartNumber=number, Body=data
            )
            parts.append({"PartNumber": number, "ETag": response["ETag"]})

        try:
            buffer = bytearray()
            async for chunk in chunks:
                buffer += chunk
                while len(buffer) >= PART_SIZE:
                    await send(bytes(buffer[:PART_SIZE]))
                    del buffer[:PART_SIZE]
            if buffer or not parts:
                await send(bytes(buffer))
            await self._client.complete_multipart_upload(
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
        except BaseException:
            await self._client.abort_multipart_upload(
                Bucket=self._bucket, Key=key, UploadId=upload_id
            )
            raise

    async def create_download_url(self, archive_id: ArchiveID, file_name: str) -> str:
        """Return a presigned URL that serves the built archive as an attachment."""
        return await self._signing_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self._bucket,
                "Key": f"{_to_archive_prefix(archive_id)}{_ARCHIVE}",
                "ResponseContentDisposition": f'attachment; filename="{file_name}"',
            },
            ExpiresIn=self._expires_in,
        )


class ManifestFile(FrozenModel):
    """A file as the manifest records it."""

    name: str
    """The file's name in the archive."""
    size: int
    """The file's size in bytes."""


class Manifest(FrozenModel):
    """An archive as it is written to the bucket when created."""

    name: str
    """The archive's name."""
    files: tuple[ManifestFile, ...]
    """The archive's files, in order."""


class S3ArchiveRepository:
    """Keeps each archive as a manifest, and reads its progress from what the bucket holds."""

    def __init__(self, client: S3Client, bucket: str, storage: FileStorage) -> None:
        """Set up the repository.

        Args:
            client: The S3 client, open for as long as the repository is used.
            bucket: The bucket that holds the archives.
            storage: Gives each file of a loaded archive its content.
        """
        self._client = client
        self._bucket = bucket
        self._storage = storage

    async def add(self, archive: Archive) -> None:
        """Write the archive's manifest."""
        manifest = Manifest(
            name=str(archive.name),
            files=tuple(
                ManifestFile(name=str(entry.name), size=entry.size) for entry in archive.entries
            ),
        )
        await self._client.put_object(
            Bucket=self._bucket,
            Key=f"{_to_archive_prefix(archive.archive_id)}{_MANIFEST}",
            Body=manifest.model_dump_json().encode(),
            ContentType="application/json",
        )

    async def get(self, archive_id: ArchiveID) -> Archive:
        """Rebuild the archive from its manifest, marking the files uploaded and whether built.

        Raises:
            ArchiveNotFoundError: The bucket holds no manifest for the ID.
        """
        archive_prefix = _to_archive_prefix(archive_id)
        try:
            response = await self._client.get_object(
                Bucket=self._bucket, Key=f"{archive_prefix}{_MANIFEST}"
            )
        except self._client.exceptions.NoSuchKey:
            raise ArchiveNotFoundError(f"No archive has the ID {archive_id}") from None
        async with response["Body"] as body:
            manifest = Manifest.model_validate_json(await body.read())

        archive = Archive(archive_id=archive_id, name=ArchiveName.model_validate(manifest.name))
        for position, file in enumerate(manifest.files):
            content = self._storage.open_file(archive_id, position)
            archive.add(EntryName.model_validate(file.name), file.size, content)

        upload_prefix = _to_upload_prefix(archive_id)
        entries = archive.entries
        for key in await self._list_keys(upload_prefix):
            position = key.removeprefix(upload_prefix)
            if position.isdigit() and int(position) < len(entries):
                archive.receive(entries[int(position)].name)
        if f"{archive_prefix}{_ARCHIVE}" in await self._list_keys(archive_prefix):
            archive.mark_built()
        return archive

    async def _list_keys(self, prefix: str) -> set[str]:
        keys: set[str] = set()
        paginator = self._client.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            keys.update(item["Key"] for item in page.get("Contents", []))
        return keys
