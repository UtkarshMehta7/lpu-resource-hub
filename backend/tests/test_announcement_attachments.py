"""Files on a notice: sniffed on the way in, scoped on the way out.

Two things are worth pinning here and both have bitten this repo's siblings.

The type comes from the BYTES. A filename and a browser's Content-Type are
both chosen by whoever uploads, so a RAR called `circular.pdf` must be stored
and served as a RAR.

And there is NO public path to the bytes. The download re-runs the notice's
own visibility check and scopes the attachment id to the notice in the path,
so another department's attachment is exactly as unreachable as its notice --
which is what makes fetching through the API client, rather than an `<a
href>`, the right call on the frontend.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.users.models import UserRole
from tests.conftest import SeededUser
from tests.test_announcements import post_draft, publish
from tests.world import World, auth, build_world

pytestmark = pytest.mark.db

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\ntrailer\n"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(64)
JPEG = b"\xff\xd8\xff" + bytes(64)
RAR = b"Rar!\x1a\x07\x00" + bytes(64)
NOT_A_FILE_WE_TAKE = b"MZ\x90\x00" + bytes(64)


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
    announcement_id: str,
    data: bytes,
    *,
    filename: str = "circular.pdf",
    declared_type: str = "application/pdf",
) -> tuple[int, dict]:
    response = client.post(
        f"/api/v1/announcements/{announcement_id}/attachments",
        headers=auth(actor),
        files={"file": (filename, data, declared_type)},
    )
    return response.status_code, response.json() if response.content else {}


def published_with_file(
    client: TestClient, world: World, data: bytes = PDF, **kwargs: str
) -> tuple[str, str]:
    """A published notice carrying one attachment. Returns (notice, attachment)."""
    notice = post_draft(client, world.admin)
    code, body = attach(client, world.admin, notice["id"], data, **kwargs)
    assert code == 201, body
    publish(client, world.admin, notice["id"])
    return str(notice["id"]), str(body["attachments"][0]["id"])


# ------------------------------------------------------------- what we take


@pytest.mark.parametrize(
    ("data", "filename", "expected_type"),
    [
        (PDF, "circular.pdf", "application/pdf"),
        (PNG, "poster.png", "image/png"),
        (JPEG, "photo.jpg", "image/jpeg"),
        (RAR, "forms.rar", "application/vnd.rar"),
    ],
)
def test_the_accepted_kinds(
    client: TestClient, world: World, data: bytes, filename: str, expected_type: str
) -> None:
    notice = post_draft(client, world.admin)

    code, body = attach(client, world.admin, notice["id"], data, filename=filename)

    assert code == 201
    assert body["attachments"][0]["content_type"] == expected_type


def test_the_type_comes_from_the_bytes_not_the_name(client: TestClient, world: World) -> None:
    """A RAR called `circular.pdf`, declared as a PDF, is stored as a RAR.

    Both the filename and the declared Content-Type are the uploader's to
    choose, so neither may decide what the institution is served.
    """
    notice = post_draft(client, world.admin)

    code, body = attach(
        client,
        world.admin,
        notice["id"],
        RAR,
        filename="circular.pdf",
        declared_type="application/pdf",
    )

    assert code == 201
    assert body["attachments"][0]["content_type"] == "application/vnd.rar"


def test_an_unsupported_type_is_refused(client: TestClient, world: World) -> None:
    notice = post_draft(client, world.admin)

    code, _ = attach(client, world.admin, notice["id"], NOT_A_FILE_WE_TAKE, filename="setup.exe")

    assert code == 415


def test_an_empty_file_is_refused(client: TestClient, world: World) -> None:
    notice = post_draft(client, world.admin)

    code, _ = attach(client, world.admin, notice["id"], b"")

    assert code == 422


def test_a_file_over_the_limit_is_refused(client: TestClient, world: World) -> None:
    notice = post_draft(client, world.admin)
    too_big = PDF + bytes(5 * 1024 * 1024)

    code, _ = attach(client, world.admin, notice["id"], too_big)

    assert code == 413


def test_the_filename_is_sanitised(client: TestClient, world: World) -> None:
    """It is a label, never a path.

    Anything outside the safe set becomes an underscore, so it cannot be read
    as a path or smuggled into the Content-Disposition header.
    """
    notice = post_draft(client, world.admin)

    _, body = attach(client, world.admin, notice["id"], PDF, filename='../../etc/"passwd".pdf')

    stored = body["attachments"][0]["filename"]
    assert "/" not in stored
    assert '"' not in stored


# --------------------------------------------------------- when it may grow


def test_only_a_draft_may_gain_an_attachment(client: TestClient, world: World) -> None:
    """Otherwise what people read and what the record holds come apart.

    409, not 403: the move exists for nobody once the notice is published.
    """
    notice = post_draft(client, world.admin)
    publish(client, world.admin, notice["id"])

    code, _ = attach(client, world.admin, notice["id"], PDF)

    assert code == 409


def test_somebody_elses_draft_cannot_gain_an_attachment(client: TestClient, world: World) -> None:
    """404, not 403: a draft is its author's alone, administrators included.

    An admin who cannot see the notice cannot be told it exists by an
    attachment refusal either.
    """
    notice = post_draft(client, world.coordinator)

    code, _ = attach(client, world.admin, notice["id"], PDF)

    assert code == 404


def test_attaching_to_a_published_notice_is_409_for_everyone(
    client: TestClient, world: World
) -> None:
    """Including an admin, who CAN see it.

    The move does not exist once the institution has read the notice, so the
    status check has to run before the authorship one -- the ordering a test
    caught the other way round in `update`.
    """
    notice = post_draft(client, world.coordinator)
    publish(client, world.coordinator, notice["id"])

    assert attach(client, world.admin, notice["id"], PDF)[0] == 409
    assert attach(client, world.coordinator, notice["id"], PDF)[0] == 409


def test_a_reader_cannot_attach_anything(client: TestClient, world: World) -> None:
    """A student cannot see the draft, so this is 404 rather than 403."""
    notice = post_draft(client, world.admin)

    code, _ = attach(client, world.student, notice["id"], PDF)

    assert code == 404


def test_an_attachment_may_be_removed_from_a_draft(client: TestClient, world: World) -> None:
    notice = post_draft(client, world.admin)
    _, body = attach(client, world.admin, notice["id"], PDF)
    attachment_id = body["attachments"][0]["id"]

    response = client.delete(
        f"/api/v1/announcements/{notice['id']}/attachments/{attachment_id}",
        headers=auth(world.admin),
    )

    assert response.status_code == 204
    remaining = client.get(
        f"/api/v1/announcements/{notice['id']}", headers=auth(world.admin)
    ).json()
    assert remaining["attachments"] == []


# ------------------------------------------------------------ the download


def test_the_file_comes_back_to_a_reader(client: TestClient, world: World) -> None:
    notice_id, attachment_id = published_with_file(client, world)

    response = client.get(
        f"/api/v1/announcements/{notice_id}/attachments/{attachment_id}",
        headers=auth(world.student),
    )

    assert response.status_code == 200
    assert response.content == PDF


def test_the_download_is_never_rendered_on_this_origin(client: TestClient, world: World) -> None:
    """An attached file must not be able to run as the application.

    `attachment` plus `nosniff` is what guarantees it, which is why the
    interface renders images from the fetched bytes instead of pointing an
    `<img src>` at this route.
    """
    notice_id, attachment_id = published_with_file(client, world, PNG, filename="poster.png")

    response = client.get(
        f"/api/v1/announcements/{notice_id}/attachments/{attachment_id}",
        headers=auth(world.student),
    )

    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, max-age=3600"


def test_the_download_requires_signing_in(client: TestClient, world: World) -> None:
    notice_id, attachment_id = published_with_file(client, world)

    assert (
        client.get(f"/api/v1/announcements/{notice_id}/attachments/{attachment_id}").status_code
        == 401
    )


def test_another_departments_file_is_unreachable(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """The file is exactly as private as the notice carrying it.

    A scoped notice whose attachment answered to whoever held the URL would be
    the thread-attachment hole all over again.
    """
    school_id = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "School of Pharmacy"}
    ).json()["id"]
    other_department_id = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": school_id, "name": "Pharmaceutics"},
    ).json()["id"]
    outsider = seed_user(UserRole.STUDENT, department_id=other_department_id)

    notice = post_draft(client, world.coordinator)
    _, body = attach(client, world.coordinator, notice["id"], PDF)
    attachment_id = body["attachments"][0]["id"]
    publish(client, world.coordinator, notice["id"])

    assert (
        client.get(
            f"/api/v1/announcements/{notice['id']}/attachments/{attachment_id}",
            headers=auth(outsider),
        ).status_code
        == 404
    )


def test_a_withdrawn_notices_file_is_unreachable(client: TestClient, world: World) -> None:
    notice_id, attachment_id = published_with_file(client, world)
    client.post(f"/api/v1/announcements/{notice_id}/withdraw", headers=auth(world.admin))

    assert (
        client.get(
            f"/api/v1/announcements/{notice_id}/attachments/{attachment_id}",
            headers=auth(world.student),
        ).status_code
        == 404
    )


def test_an_attachment_id_is_scoped_to_its_notice(client: TestClient, world: World) -> None:
    """A real attachment id on the wrong notice is a 404.

    Without the scope, the path would be decoration and any id would do --
    the trap the conversation attachment route documents.
    """
    _, attachment_id = published_with_file(client, world)
    other = post_draft(client, world.admin, subject="A different notice")
    publish(client, world.admin, other["id"])

    assert (
        client.get(
            f"/api/v1/announcements/{other['id']}/attachments/{attachment_id}",
            headers=auth(world.student),
        ).status_code
        == 404
    )


def test_a_missing_attachment_is_404(client: TestClient, world: World) -> None:
    notice_id, _ = published_with_file(client, world)

    assert (
        client.get(
            f"/api/v1/announcements/{notice_id}/attachments/{uuid.uuid4()}",
            headers=auth(world.student),
        ).status_code
        == 404
    )


def test_the_board_does_not_carry_the_bytes(client: TestClient, world: World) -> None:
    """A page of notices lists filenames, never file contents.

    Selecting `data` to print a name would drag every attached file through
    the response layer.
    """
    published_with_file(client, world)

    body = client.get("/api/v1/announcements", headers=auth(world.student)).json()

    attachment = body["items"][0]["attachments"][0]
    assert attachment["filename"] == "circular.pdf"
    assert attachment["byte_size"] == len(PDF)
    assert "data" not in attachment
