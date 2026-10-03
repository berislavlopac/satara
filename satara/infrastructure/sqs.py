"""A message queue on SQS."""

import json
from typing import TYPE_CHECKING

from satara.common.logging import get_logger
from satara.common.queue import QueueMessage

if TYPE_CHECKING:
    from types_aiobotocore_sqs import SQSClient


log = get_logger(__name__)


class SQSMessageQueue:
    """An SQS queue, received from with long polling."""

    def __init__(
        self, client: SQSClient, queue_url: str, batch_size: int = 10, wait_seconds: int = 5
    ) -> None:
        """Set up the queue.

        Args:
            client: The SQS client, open for as long as the queue is used.
            queue_url: The queue's URL.
            batch_size: The most messages to receive at once; SQS allows up to 10.
            wait_seconds: How long to wait for a message before answering with none.
        """
        self._client = client
        self._queue_url = queue_url
        self._batch_size = batch_size
        self._wait_seconds = wait_seconds

    async def receive(self) -> list[QueueMessage]:
        """Wait up to `wait_seconds` for a batch of messages."""
        response = await self._client.receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=self._batch_size,
            WaitTimeSeconds=self._wait_seconds,
            MessageSystemAttributeNames=["ApproximateReceiveCount"],
        )
        messages = [
            QueueMessage(
                body=message.get("Body", ""),
                handle=message["ReceiptHandle"],
                attempt=int(message.get("Attributes", {}).get("ApproximateReceiveCount", "1")),
            )
            for message in response.get("Messages", [])
        ]
        if messages:
            log.debug("Messages received.", count=len(messages))
        return messages

    async def delete(self, message: QueueMessage) -> None:
        """Delete the message, so that it is not delivered again."""
        await self._client.delete_message(
            QueueUrl=self._queue_url, ReceiptHandle=message.handle
        )

    async def read_max_attempts(self) -> int | None:
        """Return the attempts after which the queue's redrive policy sets a message aside."""
        response = await self._client.get_queue_attributes(
            QueueUrl=self._queue_url, AttributeNames=["RedrivePolicy"]
        )
        policy = response.get("Attributes", {}).get("RedrivePolicy")
        return int(json.loads(policy)["maxReceiveCount"]) if policy else None
