"""Files shared in a conversation.

The upload half is ordinary. The half worth testing is the download: a thread
is private, and that is worth nothing if the files in it can be fetched by
anyone holding a URL. So the cases that matter most here are the 404s.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from collections.abc import Callable, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import SeededUser
from tests.world import World, auth, build_world

pytestmark = pytest.mark.db

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\ntrailer\n"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(64)
RAR = b"Rar!\x1a\x07\x00" + bytes(64)


def _docx() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    return buffer.getvalue()


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    return build_world(client, seed_user)


@pytest.fixture
def thread_id(client: TestClient, world: World) -> str:
    """The project team's thread, with the student on the team."""
    client.post(
        f"/api/v1/projects/{world.project_id}/members",
        headers=auth(world.faculty),
        json={"user_id": str(world.student.id), "member_role": "Research assistant"},
    )
    threads = client.get("/api/v1/me/conversations", headers=auth(world.student)).json()
    first: str = threads[0]["id"]
    return first


def _upload(
    client: TestClient,
    actor: SeededUser,
    thread: str,
    data: bytes,
    filename: str = "survey.pdf",
    caption: str = "",
) -> httpx.Response:
    return client.post(
        f"/api/v1/conversations/{thread}/attachments",
        headers=auth(actor),
        files={"file": (filename, data, "application/octet-stream")},
        data={"caption": caption},
    )


# ------------------------------------------------------------------- sharing


def test_a_member_shares_a_file_and_the_team_sees_it(
    client: TestClient, world: World, thread_id: str
) -> None:
    sent = _upload(client, world.student, thread_id, PDF, caption="Last year's survey")

    assert sent.status_code == 201, sent.json()
    message = sent.json()
    assert message["body"] == "Last year's survey"
    assert len(message["attachments"]) == 1
    assert message["attachments"][0]["filename"] == "survey.pdf"
    assert message["attachments"][0]["content_type"] == "application/pdf"
    assert message["attachments"][0]["byte_size"] == len(PDF)

    page = client.get(
        f"/api/v1/conversations/{thread_id}/messages", headers=auth(world.faculty)
    ).json()
    assert page["items"][-1]["attachments"][0]["filename"] == "survey.pdf"


def test_a_file_needs_no_caption(client: TestClient, world: World, thread_id: str) -> None:
    sent = _upload(client, world.student, thread_id, PNG, filename="plot.png")

    assert sent.status_code == 201, sent.json()
    assert sent.json()["body"] == ""
    assert sent.json()["attachments"][0]["content_type"] == "image/png"


@pytest.mark.parametrize(
    ("data", "filename", "content_type"),
    [
        (PDF, "paper.pdf", "application/pdf"),
        (PNG, "figure.png", "image/png"),
        (
            _docx(),
            "notes.docx",
            ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ),
        (RAR, "dataset.rar", "application/vnd.rar"),
    ],
)
def test_every_accepted_type_goes_through(
    client: TestClient,
    world: World,
    thread_id: str,
    data: bytes,
    filename: str,
    content_type: str,
) -> None:
    sent = _upload(client, world.student, thread_id, data, filename=filename)

    assert sent.status_code == 201, sent.json()
    assert sent.json()["attachments"][0]["content_type"] == content_type


def test_the_stored_type_follows_the_bytes_not_the_name(
    client: TestClient, world: World, thread_id: str
) -> None:
    """An archive uploaded as "report.pdf" is stored as an archive. Believing
    the name would mean handing a browser a file under a type it is not."""
    sent = _upload(client, world.student, thread_id, RAR, filename="report.pdf")

    attachment = sent.json()["attachments"][0]
    assert attachment["content_type"] == "application/vnd.rar"
    assert attachment["filename"] == "report.rar"


# ------------------------------------------------------------------ refusals


def test_an_unsupported_type_is_refused(client: TestClient, world: World, thread_id: str) -> None:
    sent = _upload(client, world.student, thread_id, b"<html><script>alert(1)</script>")

    assert sent.status_code == 415, sent.json()


def test_a_file_over_the_limit_is_refused(client: TestClient, world: World, thread_id: str) -> None:
    oversized = PDF + bytes(5 * 1024 * 1024)
    sent = _upload(client, world.student, thread_id, oversized)

    assert sent.status_code == 413, sent.json()


def test_an_empty_file_is_refused(client: TestClient, world: World, thread_id: str) -> None:
    sent = _upload(client, world.student, thread_id, b"")

    assert sent.status_code == 422, sent.json()


def test_someone_outside_the_thread_cannot_upload_to_it(
    client: TestClient, world: World, thread_id: str
) -> None:
    sent = _upload(client, world.other_student, thread_id, PDF)

    assert sent.status_code == 404


# ----------------------------------------------------------------- downloads


def _share(client: TestClient, world: World, thread_id: str) -> tuple[str, str]:
    sent = _upload(client, world.student, thread_id, PDF).json()
    message_id: str = sent["id"]
    attachment_id: str = sent["attachments"][0]["id"]
    return message_id, attachment_id


def test_a_participant_downloads_the_file(client: TestClient, world: World, thread_id: str) -> None:
    _, attachment_id = _share(client, world, thread_id)

    got = client.get(
        f"/api/v1/conversations/{thread_id}/attachments/{attachment_id}",
        headers=auth(world.faculty),
    )

    assert got.status_code == 200
    assert got.content == PDF
    # Never rendered on this origin, whatever the file turns out to contain.
    assert got.headers["content-disposition"].startswith("attachment;")
    assert got.headers["x-content-type-options"] == "nosniff"
    assert "private" in got.headers["cache-control"]


def test_a_non_participant_gets_404_not_403(
    client: TestClient, world: World, thread_id: str
) -> None:
    """403 would confirm the file exists in a thread they cannot see."""
    _, attachment_id = _share(client, world, thread_id)

    refused = client.get(
        f"/api/v1/conversations/{thread_id}/attachments/{attachment_id}",
        headers=auth(world.other_student),
    )

    assert refused.status_code == 404


def test_an_administrator_gets_404_as_well(
    client: TestClient, world: World, thread_id: str
) -> None:
    """Admins read no private thread, so admins download no private file."""
    _, attachment_id = _share(client, world, thread_id)

    refused = client.get(
        f"/api/v1/conversations/{thread_id}/attachments/{attachment_id}",
        headers=auth(world.admin),
    )

    assert refused.status_code == 404


def test_an_attachment_cannot_be_fetched_through_another_thread(
    client: TestClient, world: World, thread_id: str
) -> None:
    """The conversation in the path is not decoration: an id is only valid
    inside the thread it belongs to."""
    _, attachment_id = _share(client, world, thread_id)
    other = client.post(
        "/api/v1/projects",
        headers=auth(world.other_faculty),
        json={"title": "Unrelated", "summary": "S", "description": "D"},
    ).json()["id"]
    other_thread = client.post(
        f"/api/v1/projects/{other}/conversation", headers=auth(world.other_faculty)
    ).json()["id"]

    refused = client.get(
        f"/api/v1/conversations/{other_thread}/attachments/{attachment_id}",
        headers=auth(world.other_faculty),
    )

    assert refused.status_code == 404


def test_an_unknown_attachment_is_404(client: TestClient, world: World, thread_id: str) -> None:
    missing = client.get(
        f"/api/v1/conversations/{thread_id}/attachments/{uuid.uuid4()}",
        headers=auth(world.student),
    )

    assert missing.status_code == 404


def test_requires_authentication(client: TestClient, world: World, thread_id: str) -> None:
    _, attachment_id = _share(client, world, thread_id)

    assert (
        client.get(f"/api/v1/conversations/{thread_id}/attachments/{attachment_id}").status_code
        == 401
    )


# ---------------------------------------------------------------- moderation


def test_hiding_a_message_withholds_its_file_too(
    client: TestClient, world: World, thread_id: str
) -> None:
    """Moderation withholds what was shared as well as what was said. Hiding
    the text and leaving the file downloadable would be no moderation at all.
    """
    message_id, attachment_id = _share(client, world, thread_id)

    # Hiding is the moderation route, not a button on a message: somebody
    # reports it and a moderator resolves the report with the content taken
    # down.
    report_id = client.post(
        "/api/v1/reports",
        headers=auth(world.faculty),
        json={
            "target_type": "message",
            "target_id": message_id,
            "reason": "Shared a file that should not be here.",
        },
    ).json()["id"]
    hidden = client.post(
        f"/api/v1/admin/reports/{report_id}/resolve",
        headers=auth(world.admin),
        json={"status": "actioned", "hide_target": True},
    )
    assert hidden.status_code == 200, hidden.text

    page = client.get(
        f"/api/v1/conversations/{thread_id}/messages", headers=auth(world.faculty)
    ).json()
    hidden_item = next(item for item in page["items"] if item["id"] == message_id)
    assert hidden_item["hidden"] is True
    assert hidden_item["attachments"] == []

    refused = client.get(
        f"/api/v1/conversations/{thread_id}/attachments/{attachment_id}",
        headers=auth(world.faculty),
    )
    assert refused.status_code == 404


# -------------------------------------------------------------------- cascade


def test_deleting_the_sender_takes_their_files_with_them(
    client: TestClient, world: World, thread_id: str
) -> None:
    """The reason the bytes hang off the message by a cascading foreign key
    rather than sitting in a shared blob table: nothing is left behind to
    collect, and nothing accumulates against the database quota."""
    _, attachment_id = _share(client, world, thread_id)

    assert (
        client.delete(f"/api/v1/users/{world.student.id}", headers=auth(world.admin)).status_code
        == 204
    )

    refused = client.get(
        f"/api/v1/conversations/{thread_id}/attachments/{attachment_id}",
        headers=auth(world.faculty),
    )
    assert refused.status_code == 404
