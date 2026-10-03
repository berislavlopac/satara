from http import HTTPStatus

import pytest

pytestmark = pytest.mark.integration

API = "http://localhost:8000"


async def test_files_uploaded_to_a_new_archive_are_counted_in_its_status(http):
    """Creates an archive through the API and uploads its files through the URLs given."""
    body = {
        "name": "report",
        "files": [{"name": "a.txt", "size": 5}, {"name": "b.txt", "size": 3}],
    }
    created = (await http.post(f"{API}/archives", json=body)).json()
    uploads = [
        await http.put(upload["url"], content=data)
        for upload, data in zip(created["uploads"], [b"hello", b"abc"], strict=True)
    ]

    response = await http.get(created["status_url"])

    assert [upload.status_code for upload in uploads] == [HTTPStatus.OK, HTTPStatus.OK]
    assert response.json()["files_received"] == 2
