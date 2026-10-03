import asyncio
import zipfile
from io import BytesIO

import pytest

pytestmark = pytest.mark.integration

API = "http://localhost:8000"


async def test_an_archive_is_built_once_all_its_files_are_uploaded(http):
    """Runs the whole deferred flow: create, upload, wait until ready, then download."""
    files = {"notes.txt": b"some notes", "data.csv": b"1,2\n3,4\n"}
    body = {
        "name": "report",
        "files": [{"name": name, "size": len(data)} for name, data in files.items()],
    }
    created = (await http.post(f"{API}/archives", json=body)).json()
    for upload in created["uploads"]:
        await http.put(upload["url"], content=files[upload["name"]])

    async with asyncio.timeout(30):
        status = (await http.get(created["status_url"])).json()
        while status["status"] == "pending":
            await asyncio.sleep(0.5)
            status = (await http.get(created["status_url"])).json()
    download = await http.get(status["download_url"])

    with zipfile.ZipFile(BytesIO(download.content)) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    assert status["status"] == "ready"
    assert contents == files
    assert download.headers["content-disposition"] == 'attachment; filename="report.zip"'
