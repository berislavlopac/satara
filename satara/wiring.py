"""Builds the service from its settings."""

from fastapi import FastAPI
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from satara.application.base import Limits, UploadRejectedError
from satara.application.direct import ArchiveService
from satara.config import Settings
from satara.infrastructure.zip import ZipArchiveWriter
from satara.presentation import handle_upload_rejected, router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the web application.

    Args:
        settings: The settings to build from; read from the environment if not given.

    Returns:
        The application, ready to be served.
    """
    settings = settings or Settings()
    app = FastAPI(title="Satara", summary="Packs uploaded files into a ZIP archive.")
    limits = Limits(
        max_files=settings.MAX_FILES,
        max_file_size=settings.MAX_FILE_SIZE,
        max_total_size=settings.MAX_TOTAL_SIZE,
    )
    app.state.archive_service = ArchiveService(ZipArchiveWriter(), limits)
    # Refuses an oversized body as it arrives, before the form parser stores it on disk.
    app.add_middleware(RequestBodyLimitMiddleware, max_body_size=settings.MAX_TOTAL_SIZE)
    app.add_exception_handler(UploadRejectedError, handle_upload_rejected)
    app.include_router(router)
    return app
