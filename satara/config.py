"""Service settings, read from the environment."""

from typing import Annotated

from pydantic import ByteSize, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MIB = 2**20

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

    MAX_FILE_SIZE: Annotated[Size, Field(le=2000 * MIB)] = ByteSize(50 * MIB)
    """The largest size of a single uploaded file; up to 2000 MiB.

    Without ZIP64 extensions, the ZIP library writes a file of at most 2 GiB, even after
    compression, which makes a file that does not compress slightly larger.
    """

    MAX_TOTAL_SIZE: Size = ByteSize(200 * MIB)
    """The largest size of a request body."""
