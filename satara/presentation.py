"""HTTP interface of the service."""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from satara.application import (
    ArchiveFilesCommand,
    ArchiveService,
    FileTooLargeError,
    TooManyFilesError,
    UploadedFile,
)

router = APIRouter()


def get_archive_service(request: Request) -> ArchiveService:
    """Return the archive service the application was built with."""
    return request.app.state.archive_service


@router.post("/archive-files", response_class=StreamingResponse)
async def archive_files(
    files: Annotated[list[UploadFile], File(description="The files to pack.")],
    service: Annotated[ArchiveService, Depends(get_archive_service)],
    name: Annotated[
        str | None,
        Form(description="The archive's name, without a suffix; generated if not given."),
    ] = None,
) -> StreamingResponse:
    """Pack the uploaded files into one archive and return it as a download."""
    command = ArchiveFilesCommand(
        # The form parser measures every file as it receives it, so the size is always set.
        files=tuple(
            UploadedFile(name=upload.filename or "", size=upload.size or 0, content=upload)
            for upload in files
        ),
        archive_name=name or None,
    )
    result = service.archive_files(command)
    return StreamingResponse(
        result.chunks,
        media_type=result.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.file_name}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/health")
async def check_health() -> dict[str, str]:
    """Report that the service is up and answering requests."""
    return {"status": "ok"}


async def handle_upload_rejected(request: Request, error: Exception) -> JSONResponse:
    """Answer a refused upload: 413 for a broken limit, 422 for anything else."""
    status = HTTPStatus.UNPROCESSABLE_CONTENT
    if isinstance(error, TooManyFilesError | FileTooLargeError):
        status = HTTPStatus.CONTENT_TOO_LARGE
    return JSONResponse({"detail": str(error)}, status_code=status)
