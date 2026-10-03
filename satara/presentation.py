"""HTTP interface of the service."""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse

from satara.application import (
    ArchiveFilesCommand,
    ArchiveService,
    FileTooLargeError,
    InvalidArchiveNameError,
    TooManyFilesError,
    UploadedFile,
)
from satara.common.models import FrozenModel

router = APIRouter()


class APIModel(FrozenModel):
    """Base class for a body the API sends or receives."""


class Refusal(APIModel):
    """A refused request."""

    detail: str
    """Why the request was refused."""


def get_archive_service(request: Request) -> ArchiveService:
    """Return the archive service the application was built with."""
    return request.app.state.archive_service


@router.post(
    "/archive-files",
    response_class=StreamingResponse,
    responses={
        HTTPStatus.OK: {
            "description": "The archive, sent as it is written.",
            "content": {"application/zip": {}},
        },
        HTTPStatus.BAD_REQUEST: {
            "model": Refusal,
            "description": "The form cannot be read, or breaks one of the parser's own limits.",
        },
        HTTPStatus.CONTENT_TOO_LARGE: {
            "model": Refusal,
            "description": "A limit is broken. A body declared too large is refused in plain "
            "text rather than JSON.",
            "content": {"text/plain": {}},
        },
    },
)
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
    """Answer a refused upload: 413 for a broken limit, 422 for anything else.

    A 422 is answered by the web framework's own validation handler, naming the form field at
    fault, so that every 422 the service sends has one form.
    """
    if isinstance(error, TooManyFilesError | FileTooLargeError):
        refusal = Refusal(detail=str(error))
        return JSONResponse(refusal.model_dump(), status_code=HTTPStatus.CONTENT_TOO_LARGE)
    field = "name" if isinstance(error, InvalidArchiveNameError) else "files"
    validation_error = RequestValidationError(
        [{"type": "value_error", "loc": ("body", field), "msg": str(error)}]
    )
    return await request_validation_exception_handler(request, validation_error)
