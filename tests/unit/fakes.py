"""Test doubles, type-checked against the protocols they stand in for.

Tests receive these through fixtures and never import them.
"""

from satara.domain import Content


class MemoryContent(Content):
    """File content held in memory, recording how far it has been read."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.position = 0

    async def read(self, size: int = -1) -> bytes:
        end = len(self.data) if size < 0 else self.position + size
        chunk = self.data[self.position : end]
        self.position += len(chunk)
        return chunk
