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

    The configuration files are pointed at a path that does not exist, so that the
    developer's own AWS configuration is never used.
    """
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

    The public address is the emulator's own, since it must reach the same storage; giving it
    still has the URLs signed by a client of their own.
    """
    settings = Settings(
        BUCKET=bucket,
        STORAGE_PUBLIC_URL=aws_endpoint if has_public_url else None,
        _env_file=None,
    )
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
    assert status.status == ArchiveStatus.READY
    assert contents == {"notes.txt": b"hello"}
