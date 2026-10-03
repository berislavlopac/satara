import pytest

from tests.unit.fakes import (
    FailingBroker,
    MemoryArchiveRepository,
    MemoryContent,
    MemoryFileStorage,
    MemoryQueue,
    RecordingBroker,
    RecordingWriter,
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
