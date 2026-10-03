from datetime import timedelta

import httpx2
import pytest
from aiobotocore.config import AioConfig
from aiobotocore.session import get_session

from satara.config import Settings
from satara.infrastructure.s3 import S3ArchiveRepository, S3FileStorage


@pytest.fixture
def settings():
    return Settings(_env_file=None)


@pytest.fixture
def client_options():
    """Connection options for the emulator in the local Compose stack.

    They are set in full, so that the developer's own AWS configuration is never used.
    """
    return {
        "endpoint_url": "http://localhost:4566",
        "region_name": "us-east-1",
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
    }


@pytest.fixture
async def s3_client(client_options):
    config = AioConfig(signature_version="s3v4")
    async with get_session().create_client("s3", config=config, **client_options) as client:
        yield client


@pytest.fixture
async def sqs_client(client_options):
    async with get_session().create_client("sqs", **client_options) as client:
        yield client


@pytest.fixture
def storage(s3_client, settings):
    return S3FileStorage(s3_client, settings.BUCKET, timedelta(minutes=5))


@pytest.fixture
def repository(s3_client, settings, storage):
    return S3ArchiveRepository(s3_client, settings.BUCKET, storage)


@pytest.fixture
async def http():
    async with httpx2.AsyncClient() as client:
        yield client
