import json
from http import HTTPStatus
from uuid import uuid4, uuid7

import pytest
from fastapi.testclient import TestClient

from satara.application.base import Limits
from satara.application.deferred import DeferredArchiveService
from satara.config import Settings
from satara.domain import ArchiveID
from satara.presentation.api import get_deferred_service
from satara.wiring import create_app


@pytest.fixture
def client(repository, storage, broker, recording_writer):
    """A client for the deferred flow, with the service built on the test doubles.

    The client is not entered as a context, so the application never starts and never opens
    its storage clients.
    """
    app = create_app(Settings(DEFERRED_ENABLED=True, DEFERRED_MAX_FILES=3, _env_file=None))
    limits = Limits(max_files=3, max_file_size=10, max_total_size=25)
    service = DeferredArchiveService(repository, storage, broker, recording_writer, limits)
    app.dependency_overrides[get_deferred_service] = lambda: service
    return TestClient(app)


def create(client, *files, name=None):
    body = {"name": name, "files": [{"name": file, "size": size} for file, size in files]}
    # Encoded here, as JSON escapes, because the test client cannot write a lone surrogate.
    headers = {"Content-Type": "application/json"}
    return client.post("/archives", content=json.dumps(body), headers=headers)


def test_create_archive_answers_with_a_URL_to_upload_each_file_to(client):
    body = {
        "name": "report",
        "files": [{"name": "notes.txt", "size": 5}, {"name": "old/notes.txt", "size": 7}],
    }

    response = client.post("/archives", json=body)

    archive_id = response.json()["archive_id"]
    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["uploads"] == [
        {"name": "notes.txt", "url": f"upload://{archive_id}/0?size=5"},
        {"name": "notes-2.txt", "url": f"upload://{archive_id}/1?size=7"},
    ]


def test_create_archive_points_to_the_status_of_the_new_archive(client):
    response = create(client, ("a.txt", 1))

    archive_id = response.json()["archive_id"]
    expected = f"http://testserver/archives/{archive_id}"
    assert (response.headers["location"], response.json()["status_url"]) == (expected, expected)


def test_create_archive_refuses_files_over_the_limit(client):
    response = create(client, ("a.txt", 11))

    assert response.status_code == HTTPStatus.CONTENT_TOO_LARGE
    assert response.json() == {"detail": "'a.txt' is 11 bytes; at most 10 are allowed"}


def test_create_archive_refuses_a_body_larger_than_its_declarations_need(client):
    """Refuses it before parsing it, allowing a body of 1 KiB for each file allowed.

    Whitespace pads a valid declaration past the limit, so only the body's size refuses.
    """
    body = json.dumps({"files": [{"name": "a.txt", "size": 1}]}) + " " * 4000
    headers = {"Content-Type": "application/json"}

    response = client.post("/archives", content=body, headers=headers)

    assert response.status_code == HTTPStatus.CONTENT_TOO_LARGE


@pytest.mark.parametrize(
    ("root_path", "path"),
    [("/api", "/api/archives"), ("/a", "/archives")],
    ids=["a path holding the prefix", "a path the prefix only begins"],
)
def test_create_archive_keeps_its_body_limit_when_served_under_a_path_prefix(
    client, root_path, path
):
    prefixed = TestClient(client.app, root_path=root_path)
    body = json.dumps({"files": [{"name": "a.txt", "size": 1}]}) + " " * 4000
    headers = {"Content-Type": "application/json"}

    response = prefixed.post(path, content=body, headers=headers)

    assert response.status_code == HTTPStatus.CONTENT_TOO_LARGE


def test_archive_files_keeps_its_own_body_limit_beside_archive_creation(client):
    """Accepts a body far over archive creation's limit, which applies to that path alone."""
    files = [("files", ("large.bin", b"x" * 10_000))]

    response = client.post("/archive-files", files=files)

    assert response.status_code == HTTPStatus.OK


@pytest.mark.parametrize(
    "name",
    ["..", "a" * 256, "\ud800.txt"],
    ids=["a directory", "a name too long", "a lone surrogate"],
)
def test_create_archive_refuses_an_unusable_file_name(client, name):
    response = create(client, (name, 1))

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["detail"][0]["loc"] == ["body", "files"]


def test_archive_status_counts_the_files_received_while_pending(client, repository):
    created = create(client, ("a.txt", 1), ("b.txt", 2)).json()
    archive = repository.archives[ArchiveID.model_validate(created["archive_id"])]
    archive.receive(archive.entries[1].name)

    response = client.get(created["status_url"])

    assert response.json() == {
        "archive_id": created["archive_id"],
        "status": "pending",
        "files_received": 1,
        "files_expected": 2,
        "download_url": None,
    }


def test_archive_status_gives_a_download_URL_once_ready(client, repository):
    created = create(client, ("a.txt", 1), name="report").json()
    repository.archives[ArchiveID.model_validate(created["archive_id"])].mark_built()

    response = client.get(created["status_url"])

    assert response.json()["status"] == "ready"
    assert response.json()["download_url"] == (
        f"download://{created['archive_id']}/report.recorded"
    )


@pytest.mark.parametrize(
    "archive_id", [uuid7(), uuid4()], ids=["unknown", "not a version 7 UUID"]
)
def test_archive_status_refuses_an_ID_no_archive_has(client, archive_id):
    response = client.get(f"/archives/{archive_id}")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_deferred_flow_is_not_served_unless_switched_on():
    client = TestClient(create_app(Settings(_env_file=None)))

    response = client.post("/archives", json={"files": [{"name": "a.txt", "size": 1}]})

    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize(
    ("debug", "traceback_shown"),
    [(True, True), (False, False)],
    ids=["debug mode", "otherwise"],
)
def test_an_unhandled_error_shows_its_traceback_only_in_debug_mode(
    failing_repository, storage, broker, recording_writer, debug, traceback_shown
):
    """Shows it in the body of the 500 response, so debug mode is never for production."""
    app = create_app(Settings(DEFERRED_ENABLED=True, DEBUG=debug, _env_file=None))
    limits = Limits(max_files=3, max_file_size=10, max_total_size=25)
    service = DeferredArchiveService(
        failing_repository, storage, broker, recording_writer, limits
    )
    app.dependency_overrides[get_deferred_service] = lambda: service
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(f"/archives/{uuid7()}")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert ("Traceback" in response.text) is traceback_shown
