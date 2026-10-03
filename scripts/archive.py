"""Archive files with a running service, in either flow, and save the ZIP it returns.

It uses only the standard library, so it runs wherever Python does:

    python scripts/archive.py notes.txt data.csv --name report
    python scripts/archive.py --deferred notes.txt data.csv --name report
"""

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import IO, Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

POLL_INTERVAL = 1.0
"""Seconds between status checks while a deferred archive is being built."""
POLL_TIMEOUT = 300.0
"""Seconds to wait for a deferred archive to be built before giving up."""


def send(
    url: str,
    data: bytes | IO[bytes] | None = None,
    method: str | None = None,
    headers: dict[str, str] | None = None,
) -> Any:  # noqa: ANN401 - the standard library's response, untyped
    """Send a request to the service or to storage, and return the open response.

    Raises:
        ValueError: The URL is not an HTTP one, such as a local file's.
    """
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Not an HTTP URL: {url}")
    request = Request(url, data=data, method=method, headers=headers or {})  # noqa: S310
    return urlopen(request)  # noqa: S310 - the scheme is checked above


def save_download(response: Any, output: Path) -> Path:  # noqa: ANN401
    """Save a download under the file name its response gives."""
    path = output / (response.headers.get_filename() or "archive.zip")
    path.write_bytes(response.read())
    return path


def archive_directly(url: str, files: list[Path], name: str | None, output: Path) -> Path:
    """Send the files in one request and save the archive returned."""
    boundary = uuid.uuid7().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
        f'filename="{file.name}"\r\n\r\n'.encode()
        + file.read_bytes()
        + b"\r\n"
        for file in files
    ]
    if name:
        field = f'Content-Disposition: form-data; name="name"\r\n\r\n{name}\r\n'
        parts.append(f"--{boundary}\r\n{field}".encode())
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    with send(f"{url}/archive-files", data=body, headers=headers) as response:
        return save_download(response, output)


def archive_deferred(url: str, files: list[Path], name: str | None, output: Path) -> Path:
    """Create an archive, upload each file to storage, wait until it is built, and save it."""
    declaration = {
        "name": name,
        "files": [{"name": file.name, "size": file.stat().st_size} for file in files],
    }
    data = json.dumps(declaration).encode()
    headers = {"Content-Type": "application/json"}
    with send(f"{url}/archives", data=data, headers=headers) as response:
        created = json.load(response)
    print(f"Created archive {created['archive_id']}; uploading {len(files)} files.")

    for file, upload in zip(files, created["uploads"], strict=True):
        with file.open("rb") as content:
            size = {"Content-Length": str(file.stat().st_size)}
            send(upload["url"], data=content, method="PUT", headers=size).close()

    deadline = time.monotonic() + POLL_TIMEOUT
    while True:
        with send(created["status_url"]) as response:
            status = json.load(response)
        if status["status"] != "pending":
            break
        if time.monotonic() > deadline:
            raise TimeoutError(f"The archive was not built within {POLL_TIMEOUT:.0f} seconds")
        time.sleep(POLL_INTERVAL)
    if status["status"] == "failed":
        raise RuntimeError("The service could not build the archive")

    with send(status["download_url"]) as response:
        return save_download(response, output)


def main() -> int:
    """Archive the files named on the command line, and say where the ZIP was saved."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path, help="The files to archive.")
    parser.add_argument("--name", help="The archive's name, without the .zip suffix.")
    parser.add_argument(
        "--deferred",
        action="store_true",
        help="Use the deferred flow: upload to storage, then fetch the built archive.",
    )
    parser.add_argument("--url", default="http://localhost:8000", help="The service's URL.")
    parser.add_argument("--output", type=Path, default=Path(), help="Where to save the ZIP.")
    arguments = parser.parse_args()

    archive = archive_deferred if arguments.deferred else archive_directly
    try:
        path = archive(arguments.url, arguments.files, arguments.name, arguments.output)
    except HTTPError as error:
        print(f"The service refused: {error.code} {error.read().decode()}", file=sys.stderr)
        return 1
    print(f"Saved {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
