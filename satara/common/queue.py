"""A message queue, read a batch at a time."""

from typing import Protocol

from satara.common.models import FrozenModel


class QueueMessage(FrozenModel):
    """A message received from a queue."""

    body: str
    """The message's content."""
    handle: str
    """What the queue needs to delete this delivery of the message."""
    attempt: int
    """Which attempt at handling the message this delivery is, counting from 1."""


class MessageQueue(Protocol):
    """A queue whose messages are received in batches and deleted once handled.

    A message received and not deleted is delivered again later.
    """

    async def receive(self) -> list[QueueMessage]:
        """Wait a short while for a batch of messages; the batch is empty if none arrive."""
        ...

    async def delete(self, message: QueueMessage) -> None:
        """Delete a handled message, so that it is not delivered again."""
        ...

    async def read_max_attempts(self) -> int | None:
        """Return how many attempts a message gets before the queue sets it aside.

        Returns:
            The number of attempts, or `None` if the queue keeps delivering a message.
        """
        ...
