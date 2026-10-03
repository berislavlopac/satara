import os
import re
import zipfile
from http import HTTPStatus
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from satara.config import MIB, Settings
from satara.wiring import create_app


@pytest.fixture
def client():
    settings = Settings(MAX_FILES=3, MAX_FILE_SIZE=MIB, MAX_TOTAL_SIZE=2 * MIB, _env_file=None)
    return TestClient(create_app(settings))


def read_back(data):
    with zipfile.ZipFile(BytesIO(data)) as zip_file:
        return [(info.filename, zip_file.read(info)) for info in zip_file.infolist()]


def test_archive_files_returns_the_uploaded_files_as_a_zip_download(client):
    files = [("files", ("notes.txt", b"alpha")), ("files", ("data/table.csv", b"1,2"))]

    response = client.post("/archive-files", files=files, data={"name": "report"})

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == 'attachment; filename="report.zip"'
    assert response.headers["cache-control"] == "no-store"
    assert "content-length" not in response.headers
    assert read_back(response.content) == [("notes.txt", b"alpha"), ("table.csv", b"1,2")]


@pytest.mark.parametrize("data", [{}, {"name": ""}], ids=["no name", "empty name"])
def test_archive_files_names_an_unnamed_archive_after_the_time_it_was_created(client, data):
    files = [("files", ("a.txt", b"a"))]

    response = client.post("/archive-files", files=files, data=data)

    assert re.fullmatch(
        r'attachment; filename="archive-\d{8}T\d{6}Z\.zip"',
        response.headers["content-disposition"],
    )


def test_archive_files_streams_a_file_of_the_largest_allowed_size_intact(client):
    content = os.urandom(MIB)

    response = client.post("/archive-files", files=[("files", ("large.bin", content))])

    assert read_back(response.content) == [("large.bin", content)]


def test_archive_files_refuses_more_files_than_the_limit(client):
    files = [("files", (f"{i}.txt", b"x")) for i in range(4)]

    response = client.post("/archive-files", files=files)

    assert response.status_code == HTTPStatus.CONTENT_TOO_LARGE
    assert response.json() == {"detail": "4 files were sent; at most 3 are allowed"}


def test_archive_files_refuses_a_file_larger_than_the_limit(client):
    files = [("files", ("large.bin", b"x" * (MIB + 1)))]

    response = client.post("/archive-files", files=files)

    assert response.status_code == HTTPStatus.CONTENT_TOO_LARGE
    assert response.json() == {
        "detail": f"'large.bin' is {MIB + 1} bytes; at most {MIB} are allowed"
    }


def test_archive_files_refuses_a_request_body_declared_larger_than_the_limit(client):
    # Each file is within its own limit; together they pass the limit on the whole body.
    files = [("files", (f"{i}.bin", b"x" * MIB)) for i in range(2)]

    response = client.post("/archive-files", files=files)

    assert response.status_code == HTTPStatus.CONTENT_TOO_LARGE
    assert response.text == "Content Too Large"


def test_archive_files_refuses_a_request_body_that_grows_past_the_limit(client):
    # A body produced by a generator is sent in chunks with no declared length, so the
    # limit can only be enforced by counting the bytes as they arrive. Each file is within
    # its own limit; together they pass the limit on the whole body.
    def body():
        for i in range(3):
            yield (
                b"--boundary\r\n"
                b'Content-Disposition: form-data; name="files"; filename="%d.bin"\r\n\r\n' % i
            )
            yield b"x" * MIB
            yield b"\r\n"
        yield b"--boundary--\r\n"

    response = client.post(
        "/archive-files",
        content=body(),
        headers={"content-type": "multipart/form-data; boundary=boundary"},
    )

    assert response.status_code == HTTPStatus.CONTENT_TOO_LARGE
    assert response.json() == {"detail": "Content Too Large"}


def test_archive_files_refuses_a_file_without_a_usable_name(client):
    files = [("files", ("..", b"x"))]

    response = client.post("/archive-files", files=files)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json() == {
        "detail": [
            {
                "type": "value_error",
                "loc": ["body", "files"],
                "msg": "'..' is not a usable file name",
            }
        ]
    }


def test_archive_files_quotes_a_refused_file_name_as_it_was_sent(client):
    files = [("files", (".", b"x"))]

    response = client.post("/archive-files", files=files)

    assert response.json()["detail"][0]["msg"] == "'.' is not a usable file name"


def test_archive_files_refuses_an_unusable_archive_name(client):
    files = [("files", ("a.txt", b"a"))]

    response = client.post("/archive-files", files=files, data={"name": "../report"})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json() == {
        "detail": [
            {
                "type": "value_error",
                "loc": ["body", "name"],
                "msg": "'../report' is not a usable archive name",
            }
        ]
    }


def test_archive_files_refuses_a_request_without_files(client):
    response = client.post("/archive-files", data={"name": "report"})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["detail"][0]["loc"] == ["body", "files"]


def test_archive_files_refuses_a_form_the_parser_cannot_read(client):
    headers = {"content-type": "multipart/form-data"}

    response = client.post("/archive-files", content=b"x", headers=headers)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {"detail": "Missing boundary in multipart."}


def test_openapi_describes_every_answer_archive_files_gives(client):
    response = client.get("/openapi.json")

    answers = response.json()["paths"]["/archive-files"]["post"]["responses"]
    assert set(answers) == {"200", "400", "413", "422"}
    assert set(answers["200"]["content"]) == {"application/zip"}


def test_health_check_answers_that_the_service_is_up(client):
    response = client.get("/health")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}
