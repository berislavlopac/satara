"""The queue consumer: turns upload notifications into checks of the archives they concern.

It handles one batch of messages at a time, so a message for an archive being built is read
only after the build, and finds it done.
"""

import asyncio
import json
from urllib.parse import unquote_plus

from pydantic import ValidationError

from satara.application.deferred import (
    CheckUploadsCommand,
    DeferredArchiveService,
    RecordBuildFailureCommand,
)
from satara.common.logging import get_logger
from satara.common.queue import MessageQueue, QueueMessage
from satara.domain import ArchiveID, ArchiveNotFoundError

_UPLOADS = "uploads/"

log = get_logger(__name__)


def to_archive_id(message: QueueMessage) -> ArchiveID | None:
    """Return the archive an upload notification concerns, or `None` for any other message.

    S3 sends one event per message, under a key it URL-encodes.
    """
    try:
        records = json.loads(message.body).get("Records", [])
        key = unquote_plus(records[0]["s3"]["object"]["key"])
    except ValueError, LookupError, AttributeError, TypeError:
        return None
    if not key.startswith(_UPLOADS):
        return None
    try:
        return ArchiveID.model_validate(key.removeprefix(_UPLOADS).partition("/")[0])
    except ValidationError:
        return None


class Consumer:
    """Reads upload notifications from the queue and checks the archives they concern."""

    def __init__(self, queue: MessageQueue, service: DeferredArchiveService) -> None:
        """Set up the consumer.

        Args:
            queue: The queue the bucket notifies of uploads.
            service: The deferred flow's service.
        """
        self._queue = queue
        self._service = service
        self._max_attempts: int | None = None

    async def run(self, stop: asyncio.Event) -> None:
        """Handle batches of messages until `stop` is set."""
        self._max_attempts = await self._queue.read_max_attempts()
        log.info("Consumer started.", max_attempts=self._max_attempts)
        while not stop.is_set():
            await self._handle(await self._queue.receive())
        log.info("Consumer stopped.")

    async def _handle(self, messages: list[QueueMessage]) -> None:
        by_archive: dict[ArchiveID, list[QueueMessage]] = {}
        for message in messages:
            archive_id = to_archive_id(message)
            if archive_id is None:
                log.info("Skipping a message that is not an upload.")
                await self._delete([message])
            else:
                by_archive.setdefault(archive_id, []).append(message)
        for archive_id, group in by_archive.items():
            await self._check(archive_id, group)

    async def _check(self, archive_id: ArchiveID, messages: list[QueueMessage]) -> None:
        log.debug("Checking the archive's uploads.", archive_id=str(archive_id))
        try:
            await self._service.check_uploads(CheckUploadsCommand(archive_id=archive_id))
        except ArchiveNotFoundError:
            # No later attempt can find it either, so the messages are dropped.
            log.warning("No archive has the ID; skipping.", archive_id=str(archive_id))
        except Exception:
            if self._is_last_attempt(messages):
                log.exception(
                    "Checking the archive failed at its last attempt.",
                    archive_id=str(archive_id),
                )
                await self._record_failure(archive_id)
            else:
                log.warning(
                    "Checking the archive failed; it will be retried.",
                    archive_id=str(archive_id),
                    exc_info=True,
                )
            return
        await self._delete(messages)

    def _is_last_attempt(self, messages: list[QueueMessage]) -> bool:
        if self._max_attempts is None:
            return False
        return max(message.attempt for message in messages) >= self._max_attempts

    async def _record_failure(self, archive_id: ArchiveID) -> None:
        try:
            await self._service.record_build_failure(
                RecordBuildFailureCommand(archive_id=archive_id)
            )
        except Exception:
            log.exception("Recording the failure failed.", archive_id=str(archive_id))

    async def _delete(self, messages: list[QueueMessage]) -> None:
        for message in messages:
            await self._queue.delete(message)
