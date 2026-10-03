"""Service settings, read from the environment."""

from datetime import timedelta
from typing import Annotated

from pydantic import ByteSize, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MIB = 2**20
GIB = 2**30

type Size = Annotated[ByteSize, Field(gt=0)]
"""A size in bytes. Read from the environment, it may carry a unit: `50MiB`, `200MB`."""


class Settings(BaseSettings):
    """Configuration root for the service.

    Values come from `SATARA_`-prefixed environment variables or a `.env` file, falling back
    to the defaults below. Other variables are ignored.
    """

    model_config = SettingsConfigDict(
        env_prefix="SATARA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    MAX_FILES: Annotated[int, Field(gt=0, le=1000)] = 100
    """The most files one request may upload; up to 1000, as the form parser refuses more."""

    MAX_FILE_SIZE: Size = ByteSize(50 * MIB)
    """The largest size of a single uploaded file."""

    MAX_TOTAL_SIZE: Size = ByteSize(200 * MIB)
    """The largest size of a request body."""

    DEFERRED_ENABLED: bool = False
    """Whether the deferred flow's endpoints are served."""

    DEFERRED_MAX_FILES: Annotated[int, Field(gt=0)] = 1000
    """The most files one deferred archive may hold."""

    DEFERRED_MAX_FILE_SIZE: Annotated[Size, Field(le=5 * GIB)] = ByteSize(5 * GIB)
    """The largest size of a file in a deferred archive; up to 5 GiB.

    S3 takes at most 5 GiB in one upload.
    """

    DEFERRED_MAX_TOTAL_SIZE: Size = ByteSize(50 * GIB)
    """The largest total size of the files in one deferred archive."""

    BUCKET: str = "satara-archive-deferred-flow-storage"
    """The bucket that holds the deferred flow's archives."""

    QUEUE: str = "satara-uploads"
    """The name of the queue the bucket notifies of each upload."""

    PRESIGNED_URL_LIFETIME: Annotated[
        timedelta, Field(gt=timedelta(0), le=timedelta(days=7))
    ] = timedelta(hours=1)
    """How long an upload or download URL stays valid; up to 7 days, the most S3 allows."""
