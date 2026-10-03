import pytest

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
