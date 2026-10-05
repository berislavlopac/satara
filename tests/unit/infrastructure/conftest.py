from datetime import timedelta

import pytest
from aiobotocore.session import get_session

from satara.infrastructure.s3 import S3ArchiveRepository, S3FileStorage


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
