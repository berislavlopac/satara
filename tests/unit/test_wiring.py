import zipfile
from io import BytesIO

import pytest

from satara.application.deferred import (
    CheckUploadsCommand,
    CreateArchiveCommand,
    DeclaredFile,
    GetArchiveStatusCommand,
)
from satara.config import Settings
from satara.domain import ArchiveStatus
from satara.wiring import open_deferred_service


@pytest.fixture
def aws_environment(monkeypatch, client_options, tmp_path):
    """Points the standard AWS variables at the emulator, as the service reads them there.

    The configuration files are pointed at a path that does not exist, and the variables that
    would override these are removed, so that the developer's own AWS configuration is never
    used.
    """
    for name in ("AWS_ENDPOINT_URL_S3", "AWS_ENDPOINT_URL_SQS", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ENDPOINT_URL", client_options["endpoint_url"])
    monkeypatch.setenv("AWS_DEFAULT_REGION", client_options["region_name"])
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", client_options["aws_access_key_id"])
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", client_options["aws_secret_access_key"])
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "credentials"))
    monkeypatch.delenv("AWS_PROFILE", raising=False)


@pytest.mark.parametrize(
    "has_public_url", [False, True], ids=["signed for the endpoint", "signed for a public URL"]
)
async def test_open_deferred_service_builds_an_archive_once_every_file_has_arrived(
    aws_environment, aws_endpoint, s3_client, bucket, http, has_public_url
):
    """Builds the service from its settings, with its storage reached through the environment.

    The public URL is another address of the emulator, so the URLs signed for it reach the same
    storage, but show which address they were signed for.
    """
    port = aws_endpoint.rsplit(":", 1)[1]
    public_url = f"http://127.0.0.1:{port}" if has_public_url else None
    settings = Settings(BUCKET=bucket, STORAGE_PUBLIC_URL=public_url, _env_file=None)
    async with open_deferred_service(settings) as service:
        files = (DeclaredFile(name="notes.txt", size=5),)
        created = await service.create_archive(CreateArchiveCommand(files=files))
        (await http.put(created.uploads[0].url, content=b"hello")).raise_for_status()

        await service.check_uploads(CheckUploadsCommand(archive_id=created.archive_id))

        status = await service.get_archive_status(
            GetArchiveStatusCommand(archive_id=created.archive_id)
        )
    download = await http.get(status.download_url)
    with zipfile.ZipFile(BytesIO(download.content)) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    signed_for = public_url or aws_endpoint
    assert (status.status, contents) == (ArchiveStatus.READY, {"notes.txt": b"hello"})
    assert created.uploads[0].url.startswith(signed_for)
    assert status.download_url.startswith(signed_for)
