"""Builds the service from its settings."""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

from aiobotocore.config import AioConfig
from aiobotocore.session import get_session
from fastapi import FastAPI
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from satara.application.base import Limits, UploadRejectedError
from satara.application.deferred import ArchiveBuilder, DeferredArchiveService
from satara.application.direct import ArchiveService
from satara.config import Settings
from satara.domain import AllFilesReceived, ArchiveNotFoundError
from satara.infrastructure.events import InProcessEventBroker
from satara.infrastructure.s3 import S3ArchiveRepository, S3FileStorage
from satara.infrastructure.zip import ZipArchiveWriter
from satara.presentation.http import (
    deferred_router,
    handle_archive_not_found,
    handle_upload_rejected,
    router,
)


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


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the web application.

    The deferred flow's endpoints are served only when it is switched on; its storage clients
    are then opened when the application starts and closed when it stops.

    Args:
        settings: The settings to build from; read from the environment if not given.

    Returns:
        The application, ready to be served.
    """
    settings = settings or Settings()

    @asynccontextmanager
    async def open_storage(app: FastAPI) -> AsyncGenerator[None]:
        async with open_deferred_service(settings) as service:
            app.state.deferred_service = service
            yield

    app = FastAPI(
        title="Satara",
        summary="Packs uploaded files into a ZIP archive.",
        lifespan=open_storage if settings.DEFERRED_ENABLED else None,
    )
    limits = Limits(
        max_files=settings.MAX_FILES,
        max_file_size=settings.MAX_FILE_SIZE,
        max_total_size=settings.MAX_TOTAL_SIZE,
    )
    app.state.archive_service = ArchiveService(ZipArchiveWriter(), limits)
    # Refuses an oversized body as it arrives, before the form parser stores it on disk.
    app.add_middleware(RequestBodyLimitMiddleware, max_body_size=settings.MAX_TOTAL_SIZE)
    app.add_exception_handler(UploadRejectedError, handle_upload_rejected)
    app.add_exception_handler(ArchiveNotFoundError, handle_archive_not_found)
    app.include_router(router)
    if settings.DEFERRED_ENABLED:
        app.include_router(deferred_router)
    return app
