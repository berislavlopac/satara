import httpx2
import pytest
from aiobotocore.config import AioConfig
from aiobotocore.session import get_session
from moto.server import ThreadedMotoServer

from tests.unit.fakes import (
    FailingBroker,
    FailingHandler,
    FailingRepository,
    MemoryArchiveRepository,
    MemoryContent,
    MemoryFileStorage,
    MemoryQueue,
    OtherEvent,
    RecordingBroker,
    RecordingHandler,
    RecordingWriter,
    SampleEvent,
)


@pytest.fixture(scope="session")
def memory_content():
    """The in-memory content class; session-scoped so that generated tests can use it."""
    return MemoryContent


@pytest.fixture
def recording_writer():
    return RecordingWriter()


@pytest.fixture
def repository():
    return MemoryArchiveRepository()


@pytest.fixture
def storage():
    return MemoryFileStorage()


@pytest.fixture
def broker():
    return RecordingBroker()


@pytest.fixture
def failing_broker():
    return FailingBroker()


@pytest.fixture
def memory_queue():
    """The in-memory queue class, built by each test with its own batches."""
    return MemoryQueue


@pytest.fixture
def sample_event():
    """The event class for tests, with a label to tell events apart."""
    return SampleEvent


@pytest.fixture
def other_event():
    """An event class other than the sample one."""
    return OtherEvent


@pytest.fixture
def recording_handler():
    """The handler class that notes each event it handles in a log it is given."""
    return RecordingHandler


@pytest.fixture
def failing_handler():
    return FailingHandler()


@pytest.fixture
def failing_repository():
    return FailingRepository()


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
async def http():
    async with httpx2.AsyncClient() as client:
        yield client
