"""Builds the service from its settings."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

from aiobotocore.config import AioConfig
from aiobotocore.session import get_session
from fastapi import FastAPI
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from satara.application.base import Limits, UploadRejectedError
from satara.application.deferred import ArchiveBuilder, DeferredArchiveService
from satara.application.direct import ArchiveService
from satara.common.logging import configure_logging, get_logger, silence_access_log
from satara.common.middleware import PathBodyLimitMiddleware
from satara.config import Settings
from satara.domain import AllFilesReceived, ArchiveNotFoundError
from satara.infrastructure.events import InProcessEventBroker
from satara.infrastructure.s3 import S3ArchiveRepository, S3FileStorage
from satara.infrastructure.sqs import SQSMessageQueue
from satara.infrastructure.zip import ZipArchiveWriter
from satara.presentation.consumer import Consumer
from satara.presentation.http import (
    deferred_router,
    handle_archive_not_found,
    handle_upload_rejected,
    router,
)

log = get_logger(__name__)

DECLARATION_SIZE = 1024
"""The body size allowed for each file declared when creating an archive, in bytes."""


@asynccontextmanager
async def open_deferred_service(settings: Settings) -> AsyncGenerator[DeferredArchiveService]:
    """Open the storage clients and build the deferred flow's service on them.

    An archive is built, through the service's broker, when a check finds all its files
    arrived. The clients take their endpoint, credentials and region from the standard AWS
    environment variables, and are closed on exit.

    Args:
        settings: The settings to build from.

    Yields:
        The service, usable until the context exits.
    """
    session = get_session()
    config = AioConfig(signature_version="s3v4")
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(session.create_client("s3", config=config))
        signing_client = None
        if settings.STORAGE_PUBLIC_URL:
            signing_client = await stack.enter_async_context(
                session.create_client(
                    "s3", config=config, endpoint_url=settings.STORAGE_PUBLIC_URL
                )
            )
        storage = S3FileStorage(
            client, settings.BUCKET, settings.PRESIGNED_URL_LIFETIME, signing_client
        )
        limits = Limits(
            max_files=settings.DEFERRED_MAX_FILES,
            max_file_size=settings.DEFERRED_MAX_FILE_SIZE,
            max_total_size=settings.DEFERRED_MAX_TOTAL_SIZE,
        )
        repository = S3ArchiveRepository(client, settings.BUCKET, storage)
        writer = ZipArchiveWriter()
        broker = InProcessEventBroker()
        broker.subscribe(AllFilesReceived, ArchiveBuilder(repository, storage, writer))
        yield DeferredArchiveService(repository, storage, broker, writer, limits)


@asynccontextmanager
async def open_consumer(settings: Settings) -> AsyncGenerator[Consumer]:
    """Open the storage and queue clients and build the consumer on them.

    Logging is configured afresh from the settings, which may come from a `.env` file that the
    first configuration, on import, could not see.

    Args:
        settings: The settings to build from.

    Yields:
        The consumer, ready to run until the context exits.
    """
    configure_logging(settings.DEBUG)
    async with (
        open_deferred_service(settings) as service,
        get_session().create_client("sqs") as sqs,
    ):
        queue_url = (await sqs.get_queue_url(QueueName=settings.QUEUE))["QueueUrl"]
        log.info("Consumer configured.", bucket=settings.BUCKET, queue=settings.QUEUE)
        log.debug("Settings in full.", **settings.model_dump(mode="json"))
        yield Consumer(SQSMessageQueue(sqs, queue_url), service)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the web application.

    The deferred flow's endpoints are served only when it is switched on; its storage clients
    are then opened when the application starts and closed when it stops. Logging is configured
    afresh from the settings, which may come from a `.env` file that the first configuration,
    on import, could not see.

    Args:
        settings: The settings to build from; read from the environment if not given.

    Returns:
        The application, ready to be served.
    """
    settings = settings or Settings()
    configure_logging(settings.DEBUG)

    @asynccontextmanager
    async def run(app: FastAPI) -> AsyncGenerator[None]:
        if settings.DEBUG:
            asyncio.get_running_loop().set_debug(True)
        if not settings.DEFERRED_ENABLED:
            yield
            return
        async with open_deferred_service(settings) as service:
            app.state.deferred_service = service
            yield

    app = FastAPI(
        title="Satara Archiver",
        summary="Packs uploaded files into a ZIP archive.",
        debug=settings.DEBUG,
        lifespan=run,
    )
    limits = Limits(
        max_files=settings.MAX_FILES,
        max_file_size=settings.MAX_FILE_SIZE,
        max_total_size=settings.MAX_TOTAL_SIZE,
    )
    app.state.archive_service = ArchiveService(ZipArchiveWriter(), limits)
    if settings.DEFERRED_ENABLED:
        # A declaration of the most files allowed needs far less than the direct flow's limit,
        # and a JSON body is parsed in memory, so creating an archive has a limit of its own.
        # Added first, it runs inside the limit below, and the inner of two limits applies.
        app.add_middleware(
            PathBodyLimitMiddleware,
            path="/archives",
            max_body_size=settings.DEFERRED_MAX_FILES * DECLARATION_SIZE,
        )
    # Refuses an oversized body as it arrives, before the form parser stores it on disk.
    app.add_middleware(RequestBodyLimitMiddleware, max_body_size=settings.MAX_TOTAL_SIZE)
    app.add_exception_handler(UploadRejectedError, handle_upload_rejected)
    app.add_exception_handler(ArchiveNotFoundError, handle_archive_not_found)
    app.include_router(router)
    if settings.DEFERRED_ENABLED:
        app.include_router(deferred_router)
    # The container's health check calls it every 30 seconds, which would swamp the access log.
    silence_access_log("/health")
    log.info(
        "Service configured.",
        deferred_enabled=settings.DEFERRED_ENABLED,
        **_to_limits_summary(settings),
    )
    log.debug("Settings in full.", **settings.model_dump(mode="json"))
    return app


def _to_limits_summary(settings: Settings) -> dict[str, object]:
    summary: dict[str, object] = {
        "max_files": settings.MAX_FILES,
        "max_file_size": settings.MAX_FILE_SIZE,
        "max_total_size": settings.MAX_TOTAL_SIZE,
    }
    if settings.DEFERRED_ENABLED:
        summary |= {
            "deferred_max_files": settings.DEFERRED_MAX_FILES,
            "deferred_max_file_size": settings.DEFERRED_MAX_FILE_SIZE,
            "deferred_max_total_size": settings.DEFERRED_MAX_TOTAL_SIZE,
            "bucket": settings.BUCKET,
        }
    return summary
