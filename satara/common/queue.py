"""A message queue, read a batch at a time."""

from typing import Protocol

from satara.common.models import FrozenModel


class QueueMessage(FrozenModel):
    """A message received from a queue."""

    body: str
    """The message's content."""
    receipt: str
    """What deletes this receipt of the message."""
    receive_count: int
    """How many times the message has been received, this time included."""


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
        """Return how many times a message is received before the queue sets it aside.

        Returns:
            The number of receives, or `None` if the queue keeps delivering a message.
        """
        ...
