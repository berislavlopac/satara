"""The HTTP interface: the endpoints of both flows and the answers to refused requests."""

from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import NonNegativeInt, ValidationError

from satara.application.base import (
    FileTooLargeError,
    InvalidArchiveNameError,
    TooManyFilesError,
    TotalTooLargeError,
)
from satara.application.deferred import (
    CreateArchiveCommand,
    DeclaredFile,
    DeferredArchiveService,
    GetArchiveStatusCommand,
)
from satara.application.direct import ArchiveFilesCommand, ArchiveService, UploadedFile
from satara.common.logging import get_logger
from satara.common.models import FrozenModel
from satara.domain import ArchiveID, ArchiveStatus

router = APIRouter()
deferred_router = APIRouter()
log = get_logger(__name__)


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
    log.debug(
        "Archiving files directly.",
        archive_id=str(result.archive_id),
        files=len(command.files),
        total_size=sum(file.size for file in command.files),
    )
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
    # The reason can quote the client's file names, so only its kind is logged by default.
    log.info("Upload refused.", refusal=type(error).__name__, path=request.url.path)
    log.debug("Upload refused.", reason=str(error))
    if isinstance(error, TooManyFilesError | FileTooLargeError | TotalTooLargeError):
        refusal = Refusal(detail=str(error))
        return JSONResponse(refusal.model_dump(), status_code=HTTPStatus.CONTENT_TOO_LARGE)
    field = "name" if isinstance(error, InvalidArchiveNameError) else "files"
    validation_error = RequestValidationError(
        [{"type": "value_error", "loc": ("body", field), "msg": str(error)}]
    )
    return await request_validation_exception_handler(request, validation_error)


async def handle_archive_not_found(request: Request, error: Exception) -> JSONResponse:
    """Answer a request for an archive that does not exist with 404."""
    log.debug("No such archive.", reason=str(error))
    refusal = Refusal(detail=str(error))
    return JSONResponse(refusal.model_dump(), status_code=HTTPStatus.NOT_FOUND)


class FileDeclaration(APIModel):
    """A file the client is about to upload."""

    name: str
    """The file's name; directories in it are dropped."""
    size: NonNegativeInt
    """The file's size in bytes; the upload must be exactly this size."""


class CreateArchiveRequest(APIModel):
    """An archive to create, and the files that will be uploaded to it."""

    name: str | None = None
    """The archive's name, without a suffix; generated if not given."""
    files: list[FileDeclaration]
    """The files, in the order they are to appear in the archive."""


class FileUploadTarget(APIModel):
    """Where to upload one file."""

    name: str
    """The file's name in the archive, renamed if another file had it first."""
    url: str
    """The URL to `PUT` the file's content to."""


class CreateArchiveResponse(APIModel):
    """A new archive, waiting for its files."""

    archive_id: UUID
    """The identity of the archive."""
    status_url: str
    """Where to follow the archive's progress."""
    uploads: list[FileUploadTarget]
    """Where to upload each file, in the order they were declared."""


class ArchiveStatusResponse(APIModel):
    """How far an archive has got."""

    archive_id: UUID
    """The identity of the archive."""
    status: ArchiveStatus
    """`pending` until the archive is built, then `ready`, or `failed` if it cannot be built."""
    files_received: int
    """How many of the archive's files have been uploaded."""
    files_expected: int
    """How many files the archive holds."""
    download_url: str | None
    """Where to download the archive, once it is ready."""


def get_deferred_service(request: Request) -> DeferredArchiveService:
    """Return the deferred flow's service, opened when the application started."""
    return request.app.state.deferred_service


@deferred_router.post(
    "/archives",
    status_code=HTTPStatus.CREATED,
    responses={
        HTTPStatus.CONTENT_TOO_LARGE: {"model": Refusal, "description": "A limit is broken."}
    },
)
async def create_archive(
    body: CreateArchiveRequest,
    request: Request,
    response: Response,
    service: Annotated[DeferredArchiveService, Depends(get_deferred_service)],
) -> CreateArchiveResponse:
    """Create an archive and answer with a URL to upload each of its files to.

    The archive is built once every file has been uploaded; follow `status_url` until it is
    ready.
    """
    command = CreateArchiveCommand(
        files=tuple(DeclaredFile(name=file.name, size=file.size) for file in body.files),
        archive_name=body.name or None,
    )
    result = await service.create_archive(command)
    status_url = str(request.url_for("get_archive_status", archive_id=str(result.archive_id)))
    response.headers["Location"] = status_url
    return CreateArchiveResponse(
        archive_id=result.archive_id.id,
        status_url=status_url,
        uploads=[
            FileUploadTarget(name=upload.name, url=upload.url) for upload in result.uploads
        ],
    )


@deferred_router.get(
    "/archives/{archive_id}",
    responses={HTTPStatus.NOT_FOUND: {"model": Refusal, "description": "No such archive."}},
)
async def get_archive_status(
    archive_id: UUID,
    service: Annotated[DeferredArchiveService, Depends(get_deferred_service)],
) -> ArchiveStatusResponse:
    """Report how far an archive has got, with a download URL once it is ready."""
    try:
        command = GetArchiveStatusCommand(archive_id=ArchiveID.model_validate(archive_id))
    except ValidationError:
        # Only a UUID of version 7 can identify an archive.
        detail = f"No archive has the ID {archive_id}"
        raise HTTPException(HTTPStatus.NOT_FOUND, detail) from None
    result = await service.get_archive_status(command)
    return ArchiveStatusResponse(
        archive_id=result.archive_id.id,
        status=result.status,
        files_received=result.files_received,
        files_expected=result.files_expected,
        download_url=result.download_url,
    )
