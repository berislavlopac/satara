"""The queue consumer: turns upload notifications into checks of the archives they concern.

Run it with `python -m satara.presentation.consumer`. It handles one batch of messages at a
time, so a message for an archive being built is read only after the build, and finds it
done. A stop signal ends the loop once the current batch is handled.
"""

import asyncio
import json
import signal
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote_plus

from aiobotocore.session import get_session
from pydantic import ValidationError

from satara.application.deferred import (
    CheckUploadsCommand,
    DeferredArchiveService,
    RecordBuildFailureCommand,
)
from satara.common.heartbeat import start_heartbeat
from satara.common.logging import get_logger
from satara.config import Settings
from satara.domain import ArchiveID
from satara.wiring import open_deferred_service

if TYPE_CHECKING:
    from types_aiobotocore_sqs import SQSClient
    from types_aiobotocore_sqs.type_defs import MessageTypeDef

HEARTBEAT_FILE = Path(tempfile.gettempdir()) / "satara-consumer-alive"
"""The file the consumer touches while it runs, for a health check to look at."""

_UPLOADS = "uploads/"

log = get_logger(__name__)


def to_archive_id(message: MessageTypeDef) -> ArchiveID | None:
    """Return the archive an upload notification concerns, or `None` for any other message.

    S3 sends one event per message, under a key it URL-encodes.
    """
    try:
        records = json.loads(message.get("Body", "")).get("Records", [])
        key = unquote_plus(records[0]["s3"]["object"]["key"])
    except ValueError, LookupError, AttributeError:
        return None
    if not key.startswith(_UPLOADS):
        return None
    try:
        return ArchiveID.model_validate(key.removeprefix(_UPLOADS).partition("/")[0])
    except ValidationError:
        return None


class Consumer:
    """Reads upload notifications from the queue and checks the archives they concern."""

    def __init__(self, sqs: SQSClient, queue_url: str, service: DeferredArchiveService) -> None:
        """Set up the consumer.

        Args:
            sqs: The queue client, open for as long as the consumer runs.
            queue_url: The queue the bucket notifies of uploads.
            service: The deferred flow's service.
        """
        self._sqs = sqs
        self._queue_url = queue_url
        self._service = service
        self._max_attempts: int | None = None

    async def run(self, stop: asyncio.Event) -> None:
        """Handle batches of messages until `stop` is set."""
        self._max_attempts = await self._read_max_attempts()
        log.info(
            "Consumer started.", queue_url=self._queue_url, max_attempts=self._max_attempts
        )
        while not stop.is_set():
            response = await self._sqs.receive_message(
                QueueUrl=self._queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=5,
                MessageSystemAttributeNames=["ApproximateReceiveCount"],
            )
            await self._handle(response.get("Messages", []))
        log.info("Consumer stopped.")

    async def _handle(self, messages: list[MessageTypeDef]) -> None:
        by_archive: dict[ArchiveID, list[MessageTypeDef]] = {}
        for message in messages:
            archive_id = to_archive_id(message)
            if archive_id is None:
                log.info("Skipping a message that is not an upload.")
                await self._delete([message])
            else:
                by_archive.setdefault(archive_id, []).append(message)
        for archive_id, group in by_archive.items():
            await self._check(archive_id, group)

    async def _check(self, archive_id: ArchiveID, messages: list[MessageTypeDef]) -> None:
        log.info("Checking the archive's uploads.", archive_id=str(archive_id))
        try:
            await self._service.check_uploads(CheckUploadsCommand(archive_id=archive_id))
        except Exception:
            log.exception("Checking the archive failed.", archive_id=str(archive_id))
            if self._is_last_attempt(messages):
                await self._record_failure(archive_id)
            return
        await self._delete(messages)

    def _is_last_attempt(self, messages: list[MessageTypeDef]) -> bool:
        if self._max_attempts is None:
            return False
        attempts = [
            int(message.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
            for message in messages
        ]
        return max(attempts) >= self._max_attempts

    async def _record_failure(self, archive_id: ArchiveID) -> None:
        try:
            await self._service.record_build_failure(
                RecordBuildFailureCommand(archive_id=archive_id)
            )
        except Exception:
            log.exception("Recording the failure failed.", archive_id=str(archive_id))

    async def _delete(self, messages: list[MessageTypeDef]) -> None:
        for message in messages:
            await self._sqs.delete_message(
                QueueUrl=self._queue_url, ReceiptHandle=message["ReceiptHandle"]
            )

    async def _read_max_attempts(self) -> int | None:
        response = await self._sqs.get_queue_attributes(
            QueueUrl=self._queue_url, AttributeNames=["RedrivePolicy"]
        )
        policy = response.get("Attributes", {}).get("RedrivePolicy")
        return int(json.loads(policy)["maxReceiveCount"]) if policy else None


async def consume(settings: Settings, stop: asyncio.Event) -> None:
    """Open the clients and run the consumer until `stop` is set.

    Args:
        settings: The settings to build from.
        stop: Set to end the consumer once its current batch is handled.
    """
    async with (
        open_deferred_service(settings) as service,
        get_session().create_client("sqs") as sqs,
    ):
        queue_url = (await sqs.get_queue_url(QueueName=settings.QUEUE))["QueueUrl"]
        await Consumer(sqs, queue_url, service).run(stop)


async def main() -> None:
    """Run the consumer, with a heartbeat, until the process is told to stop."""
    start_heartbeat(HEARTBEAT_FILE)
    stop = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)
    await consume(Settings(), stop)


if __name__ == "__main__":
    asyncio.run(main())
