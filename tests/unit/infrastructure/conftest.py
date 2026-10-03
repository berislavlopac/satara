from datetime import timedelta

import httpx2
import pytest
from aiobotocore.config import AioConfig
from aiobotocore.session import get_session
from moto.server import ThreadedMotoServer

from satara.infrastructure.s3 import S3ArchiveRepository, S3FileStorage


@pytest.fixture(scope="session")
def aws_endpoint():
    """An AWS emulator run inside the test process, so the adapters need no Docker."""
    server = ThreadedMotoServer(port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    yield f"http://{host}:{port}"
    server.stop()


@pytest.fixture
def client_options(aws_endpoint):
    """Connection options for the emulator, with each test starting from an empty one.

    They are set in full, so that the developer's own AWS configuration is never used.
    """
    httpx2.post(f"{aws_endpoint}/moto-api/reset").raise_for_status()
    return {
        "endpoint_url": aws_endpoint,
        "region_name": "us-east-1",
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
    }


@pytest.fixture
def bucket():
    return "satara-test-bucket"


@pytest.fixture
async def s3_client(client_options, bucket):
    config = AioConfig(signature_version="s3v4")
    async with get_session().create_client("s3", config=config, **client_options) as client:
        await client.create_bucket(Bucket=bucket)
        yield client


@pytest.fixture
async def sqs_client(client_options):
    async with get_session().create_client("sqs", **client_options) as client:
        yield client


@pytest.fixture
def s3_storage(s3_client, bucket):
    return S3FileStorage(s3_client, bucket, timedelta(minutes=5))


@pytest.fixture
def s3_repository(s3_client, bucket, s3_storage):
    return S3ArchiveRepository(s3_client, bucket, s3_storage)


@pytest.fixture
async def http():
    async with httpx2.AsyncClient() as client:
        yield client
