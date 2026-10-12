"""Supporting documents on a request.

Two things are pinned here, both of which have bitten this repo's siblings:
the type comes from the BYTES, never the filename or the declared
Content-Type; and there is no public path to the bytes -- the download runs
the request's own visibility check, so a document is exactly as private as
the request carrying it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import SeededUser
from tests.test_personal_requests import a_request, move
from tests.world import World, auth, build_world

pytestmark = pytest.mark.db

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\ntrailer\n"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(64)
NOT_TAKEN = b"MZ\x90\x00" + bytes(64)


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    return build_world(client, seed_user)


def attach(
    client: TestClient,
    actor: SeededUser,
    request_id: str,
    data: bytes,
    *,
    filename: str = "form.pdf",
    declared: str = "application/pdf",
) -> tuple[int, dict]:
    response = client.post(
        f"/api/v1/requests/{request_id}/attachments",
        headers=auth(actor),
        files={"file": (filename, data, declared)},
    )
    return response.status_code, response.json() if response.content else {}


def with_file(client: TestClient, world: World, data: bytes = PDF, **kw: str) -> tuple[str, str]:
    request_id = a_request(client, world)
    code, body = attach(client, world.student, request_id, data, **kw)
    assert code == 201, body
    return request_id, str(body["attachments"][0]["id"])


def test_the_sender_attaches_a_supporting_document(client: TestClient, world: World) -> None:
    request_id, _ = with_file(client, world)

    body = client.get(f"/api/v1/requests/{request_id}", headers=auth(world.faculty)).json()

    assert [a["filename"] for a in body["attachments"]] == ["form.pdf"]


def test_the_type_comes_from_the_bytes(client: TestClient, world: World) -> None:
    """A PNG called form.pdf and declared as a PDF is stored as a PNG."""
    request_id = a_request(client, world)

    _, body = attach(client, world.student, request_id, PNG, filename="form.pdf")

    assert body["attachments"][0]["content_type"] == "image/png"
    assert body["attachments"][0]["filename"].endswith(".png")


def test_an_unsupported_type_is_refused(client: TestClient, world: World) -> None:
    request_id = a_request(client, world)

    assert attach(client, world.student, request_id, NOT_TAKEN, filename="x.exe")[0] == 415


def test_an_empty_file_is_refused(client: TestClient, world: World) -> None:
    request_id = a_request(client, world)

    assert attach(client, world.student, request_id, b"")[0] == 422


def test_a_file_over_the_limit_is_refused(client: TestClient, world: World) -> None:
    request_id = a_request(client, world)

    assert attach(client, world.student, request_id, PDF + bytes(5 * 1024 * 1024))[0] == 413


def test_only_the_sender_attaches(client: TestClient, world: World) -> None:
    """The recipient answers; they do not add to what they were asked."""
    request_id = a_request(client, world)

    assert attach(client, world.faculty, request_id, PDF)[0] == 403


def test_a_third_party_cannot_attach_or_even_find_it(client: TestClient, world: World) -> None:
    request_id = a_request(client, world)

    assert attach(client, world.admin, request_id, PDF)[0] == 404


def test_nothing_may_be_added_once_it_is_decided(client: TestClient, world: World) -> None:
    """409 for everyone, including the sender.

    Adding to a decided request changes what the other party answered, after
    they answered it.
    """
    request_id, _ = with_file(client, world)
    move(client, world.faculty, request_id, "resolved")

    assert attach(client, world.student, request_id, PDF)[0] == 409


def test_the_sender_may_remove_one_while_it_is_open(client: TestClient, world: World) -> None:
    request_id, attachment_id = with_file(client, world)

    response = client.delete(
        f"/api/v1/requests/{request_id}/attachments/{attachment_id}",
        headers=auth(world.student),
    )

    assert response.status_code == 204
    body = client.get(f"/api/v1/requests/{request_id}", headers=auth(world.student)).json()
    assert body["attachments"] == []


def test_the_recipient_may_download_it(client: TestClient, world: World) -> None:
    request_id, attachment_id = with_file(client, world)

    response = client.get(
        f"/api/v1/requests/{request_id}/attachments/{attachment_id}",
        headers=auth(world.faculty),
    )

    assert response.status_code == 200
    assert response.content == PDF


def test_the_download_is_never_rendered_on_this_origin(client: TestClient, world: World) -> None:
    request_id, attachment_id = with_file(client, world, PNG, filename="scan.png")

    response = client.get(
        f"/api/v1/requests/{request_id}/attachments/{attachment_id}",
        headers=auth(world.faculty),
    )

    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, max-age=3600"


def test_nobody_else_reaches_the_bytes(client: TestClient, world: World) -> None:
    """Administrators included. A request is between two people."""
    request_id, attachment_id = with_file(client, world)
    path = f"/api/v1/requests/{request_id}/attachments/{attachment_id}"

    for outsider in (world.admin, world.coordinator, world.other_student):
        assert client.get(path, headers=auth(outsider)).status_code == 404
    assert client.get(path).status_code == 401


def test_an_attachment_id_is_scoped_to_its_request(client: TestClient, world: World) -> None:
    """A real id on the wrong request is a 404, or the path is decoration."""
    _, attachment_id = with_file(client, world)
    other_id = a_request(client, world)

    assert (
        client.get(
            f"/api/v1/requests/{other_id}/attachments/{attachment_id}",
            headers=auth(world.student),
        ).status_code
        == 404
    )


def test_a_missing_attachment_is_404(client: TestClient, world: World) -> None:
    request_id, _ = with_file(client, world)

    assert (
        client.get(
            f"/api/v1/requests/{request_id}/attachments/{uuid.uuid4()}",
            headers=auth(world.student),
        ).status_code
        == 404
    )


def test_a_list_never_carries_the_bytes(client: TestClient, world: World) -> None:
    with_file(client, world)

    body = client.get("/api/v1/requests/inbox", headers=auth(world.faculty)).json()

    attachment = body["items"][0]["attachments"][0]
    assert attachment["byte_size"] == len(PDF)
    assert "data" not in attachment
