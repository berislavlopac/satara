import pytest

from tests.unit.fakes import MemoryContent, RecordingWriter


@pytest.fixture(scope="session")
def memory_content():
    """The in-memory content class; session-scoped so that generated tests can use it."""
    return MemoryContent


@pytest.fixture
def recording_writer():
    return RecordingWriter()
