"""Conversation threads: who may read them, and what the cascade really does.

Threads are scoped on purpose. There is no endpoint that opens one between two
arbitrary people, so the tests that matter most are the ones proving a thread
cannot be reached by someone it does not belong to -- and that the answer is
404, not 403. A 403 on a thread id would confirm that two named people are
talking, which is the one fact a private thread exists to keep.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import SeededUser
from tests.world import World, auth, build_world

pytestmark = pytest.mark.db


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    return build_world(client, seed_user)


def _accepted_thread(client: TestClient, world: World) -> str:
    """A student asks the faculty member to collaborate; they accept."""
    request_id = client.post(
        "/api/v1/collaborations",
        headers=auth(world.student),
        json={"recipient_id": str(world.faculty.id), "message": "May I join the sensor work?"},
    ).json()["id"]
    accepted = client.post(
        f"/api/v1/collaborations/{request_id}/accept", headers=auth(world.faculty)
    )
    assert accepted.status_code == 200, accepted.json()

    threads = client.get("/api/v1/me/conversations", headers=auth(world.student)).json()
    assert len(threads) == 1, threads
    thread_id: str = threads[0]["id"]
    return thread_id


def _send(client: TestClient, actor: SeededUser, thread_id: str, body: str) -> dict[str, object]:
    response = client.post(
        f"/api/v1/conversations/{thread_id}/messages",
        headers=auth(actor),
        json={"body": body},
    )
    assert response.status_code == 201, response.json()
    result: dict[str, object] = response.json()
    return result


# ------------------------------------------------- a thread exists only once agreed


def test_accepting_a_request_opens_a_thread(client: TestClient, world: World) -> None:
    thread_id = _accepted_thread(client, world)

    for actor in (world.student, world.faculty):
        body = client.get(f"/api/v1/conversations/{thread_id}", headers=auth(actor)).json()
        assert body["subject_kind"] == "collaboration"
        # Named after the other person, not after itself.
        assert body["title"]
        assert len(body["participants"]) == 2


def test_a_pending_request_has_no_thread(client: TestClient, world: World) -> None:
    client.post(
        "/api/v1/collaborations",
        headers=auth(world.student),
        json={"recipient_id": str(world.faculty.id), "message": "Hello?"},
    )

    assert client.get("/api/v1/me/conversations", headers=auth(world.student)).json() == []


def test_a_declined_request_has_no_thread(client: TestClient, world: World) -> None:
    """Saying no must not hand the sender a channel anyway."""
    request_id = client.post(
        "/api/v1/collaborations",
        headers=auth(world.student),
        json={"recipient_id": str(world.faculty.id), "message": "Hello?"},
    ).json()["id"]
    client.post(f"/api/v1/collaborations/{request_id}/decline", headers=auth(world.faculty))

    assert client.get("/api/v1/me/conversations", headers=auth(world.student)).json() == []


def test_there_is_no_endpoint_that_creates_a_thread(client: TestClient, world: World) -> None:
    """The whole safety property: a client cannot conjure a channel."""
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/conversations" not in paths
    assert not [
        path
        for path, operations in paths.items()
        if path.startswith("/api/v1/conversations") and "post" in operations and "{" not in path
    ]


# --------------------------------------------------------- 404, never 403


def test_an_outsider_cannot_tell_the_thread_exists(client: TestClient, world: World) -> None:
    thread_id = _accepted_thread(client, world)

    for path in (
        f"/api/v1/conversations/{thread_id}",
        f"/api/v1/conversations/{thread_id}/messages",
    ):
        response = client.get(path, headers=auth(world.other_student))
        assert response.status_code == 404, f"{path} leaked {response.status_code}"


def test_an_outsider_cannot_write_into_a_thread(client: TestClient, world: World) -> None:
    thread_id = _accepted_thread(client, world)

    response = client.post(
        f"/api/v1/conversations/{thread_id}/messages",
        headers=auth(world.other_student),
        json={"body": "let me in"},
    )

    assert response.status_code == 404


def test_an_admin_is_not_an_exception(client: TestClient, world: World) -> None:
    """Moderating a reported message is not the same as reading the thread."""
    thread_id = _accepted_thread(client, world)

    assert (
        client.get(f"/api/v1/conversations/{thread_id}", headers=auth(world.admin)).status_code
        == 404
    )


def test_an_unknown_thread_is_also_404(client: TestClient, world: World) -> None:
    response = client.get(f"/api/v1/conversations/{uuid.uuid4()}", headers=auth(world.student))

    assert response.status_code == 404


def test_signing_in_is_required(client: TestClient, world: World) -> None:
    thread_id = _accepted_thread(client, world)

    assert client.get(f"/api/v1/conversations/{thread_id}").status_code == 401


# ------------------------------------------------------------- reading and writing


def test_messages_come_back_oldest_first_with_the_sender_named(
    client: TestClient, world: World
) -> None:
    thread_id = _accepted_thread(client, world)
    _send(client, world.student, thread_id, "First")
    _send(client, world.faculty, thread_id, "Second")

    page = client.get(
        f"/api/v1/conversations/{thread_id}/messages", headers=auth(world.student)
    ).json()

    assert [item["body"] for item in page["items"]] == ["First", "Second"]
    # The UID travels with every name (ADR 0020).
    assert all(item["sender_registration_number"] for item in page["items"])


def test_the_cursor_returns_only_what_is_new(client: TestClient, world: World) -> None:
    """What the poll depends on: an open thread costs one small query."""
    thread_id = _accepted_thread(client, world)
    _send(client, world.student, thread_id, "First")
    page = client.get(
        f"/api/v1/conversations/{thread_id}/messages", headers=auth(world.student)
    ).json()

    empty = client.get(
        f"/api/v1/conversations/{thread_id}/messages",
        headers=auth(world.student),
        params={"after": page["next_after"]},
    ).json()
    assert empty["items"] == []

    _send(client, world.faculty, thread_id, "Second")
    fresh = client.get(
        f"/api/v1/conversations/{thread_id}/messages",
        headers=auth(world.student),
        params={"after": page["next_after"]},
    ).json()
    assert [item["body"] for item in fresh["items"]] == ["Second"]


def test_a_nonsense_cursor_replays_the_thread_instead_of_failing(
    client: TestClient, world: World
) -> None:
    """A stale client recovers by itself rather than showing an error."""
    thread_id = _accepted_thread(client, world)
    _send(client, world.student, thread_id, "First")

    page = client.get(
        f"/api/v1/conversations/{thread_id}/messages",
        headers=auth(world.student),
        params={"after": "not-a-cursor"},
    )

    assert page.status_code == 200
    assert len(page.json()["items"]) == 1


def test_an_empty_message_is_refused(client: TestClient, world: World) -> None:
    thread_id = _accepted_thread(client, world)

    response = client.post(
        f"/api/v1/conversations/{thread_id}/messages",
        headers=auth(world.student),
        json={"body": "   "},
    )

    assert response.status_code == 422


def test_an_overlong_message_is_refused(client: TestClient, world: World) -> None:
    thread_id = _accepted_thread(client, world)

    response = client.post(
        f"/api/v1/conversations/{thread_id}/messages",
        headers=auth(world.student),
        json={"body": "x" * 4001},
    )

    assert response.status_code == 422


# ------------------------------------------------------------------- unread


def test_unread_counts_the_other_persons_messages_only(client: TestClient, world: World) -> None:
    thread_id = _accepted_thread(client, world)
    _send(client, world.student, thread_id, "Mine")

    mine = client.get("/api/v1/me/conversations", headers=auth(world.student)).json()[0]
    theirs = client.get("/api/v1/me/conversations", headers=auth(world.faculty)).json()[0]

    assert mine["unread_count"] == 0, "your own message is not news to you"
    assert theirs["unread_count"] == 1


def test_reading_a_thread_clears_its_unread_count(client: TestClient, world: World) -> None:
    thread_id = _accepted_thread(client, world)
    _send(client, world.student, thread_id, "Hello")

    client.post(f"/api/v1/conversations/{thread_id}/read", headers=auth(world.faculty))

    after = client.get("/api/v1/me/conversations", headers=auth(world.faculty)).json()[0]
    assert after["unread_count"] == 0
    assert (
        client.get("/api/v1/me/conversations/unread-count", headers=auth(world.faculty)).json() == 0
    )


def test_the_list_is_ordered_by_the_latest_activity(client: TestClient, world: World) -> None:
    thread_id = _accepted_thread(client, world)
    _send(client, world.student, thread_id, "Only thread")

    listed = client.get("/api/v1/me/conversations", headers=auth(world.student)).json()

    assert listed[0]["id"] == thread_id
    assert listed[0]["preview"] == "Only thread"
    assert listed[0]["last_message_at"] is not None


# ------------------------------------------------------- one notification per thread


def _message_notices(client: TestClient, actor: SeededUser) -> list[dict[str, object]]:
    body = client.get("/api/v1/me/notifications", headers=auth(actor)).json()
    items = body["items"] if isinstance(body, dict) else body
    return [item for item in items if item["notification_type"] == "message_received"]


def test_many_messages_make_one_notification(client: TestClient, world: World) -> None:
    """Twenty messages must not bury the bell under twenty lines."""
    thread_id = _accepted_thread(client, world)
    for index in range(5):
        _send(client, world.student, thread_id, f"Message {index}")

    assert len(_message_notices(client, world.faculty)) == 1


def test_reading_re_arms_the_notification(client: TestClient, world: World) -> None:
    """A message after a lull is still announced."""
    thread_id = _accepted_thread(client, world)
    _send(client, world.student, thread_id, "First")
    assert len(_message_notices(client, world.faculty)) == 1

    client.post(f"/api/v1/conversations/{thread_id}/read", headers=auth(world.faculty))
    assert _message_notices(client, world.faculty) == [], "reading clears the notice"

    _send(client, world.student, thread_id, "Second")
    assert len(_message_notices(client, world.faculty)) == 1


def test_the_sender_is_not_notified_of_their_own_message(client: TestClient, world: World) -> None:
    thread_id = _accepted_thread(client, world)
    _send(client, world.student, thread_id, "Hello")

    assert _message_notices(client, world.student) == []


# ------------------------------------------------------------------ moderation


def test_a_hidden_message_stays_in_the_thread(client: TestClient, world: World) -> None:
    """Hidden, not deleted: the exchange still reads in order."""
    thread_id = _accepted_thread(client, world)
    first = _send(client, world.student, thread_id, "Fine message")
    offending = _send(client, world.student, thread_id, "Rude message")
    _send(client, world.faculty, thread_id, "Reply")

    report_id = client.post(
        "/api/v1/reports",
        headers=auth(world.faculty),
        json={
            "target_type": "message",
            "target_id": offending["id"],
            "reason": "Abusive language in a thread",
        },
    ).json()["id"]
    resolved = client.post(
        f"/api/v1/admin/reports/{report_id}/resolve",
        headers=auth(world.admin),
        json={"status": "actioned", "hide_target": True, "note": "Hidden"},
    )
    assert resolved.status_code == 200, resolved.json()

    page = client.get(
        f"/api/v1/conversations/{thread_id}/messages", headers=auth(world.faculty)
    ).json()
    assert len(page["items"]) == 3, "still three messages, no hole"
    hidden = [item for item in page["items"] if item["hidden"]]
    assert len(hidden) == 1
    assert hidden[0]["body"] is None, "the text is withheld"
    assert page["items"][0]["body"] == "Fine message"
    assert first["id"] != hidden[0]["id"]


def test_a_hidden_message_leaves_no_preview(client: TestClient, world: World) -> None:
    """The list must not be a way to read around a moderator's decision."""
    thread_id = _accepted_thread(client, world)
    offending = _send(client, world.student, thread_id, "Rude message")
    report_id = client.post(
        "/api/v1/reports",
        headers=auth(world.faculty),
        json={
            "target_type": "message",
            "target_id": offending["id"],
            "reason": "Abusive language in a thread",
        },
    ).json()["id"]
    client.post(
        f"/api/v1/admin/reports/{report_id}/resolve",
        headers=auth(world.admin),
        json={"status": "actioned", "hide_target": True, "note": "Hidden"},
    )

    listed = client.get("/api/v1/me/conversations", headers=auth(world.faculty)).json()[0]

    assert listed["preview"] is None


def test_reporting_a_message_requires_being_in_the_thread(client: TestClient, world: World) -> None:
    """Otherwise reporting is a way to ask whether a message id is real."""
    thread_id = _accepted_thread(client, world)
    message = _send(client, world.student, thread_id, "Private")

    response = client.post(
        "/api/v1/reports",
        headers=auth(world.other_student),
        json={
            "target_type": "message",
            "target_id": message["id"],
            "reason": "Just curious whether this exists",
        },
    )

    assert response.status_code == 404


# ------------------------------------------------------------- project threads


def test_a_project_team_shares_a_thread(client: TestClient, world: World) -> None:
    opened = client.post(
        f"/api/v1/projects/{world.project_id}/conversation", headers=auth(world.faculty)
    )

    assert opened.status_code == 200, opened.json()
    assert opened.json()["subject_kind"] == "project"
    # Idempotent: the button does not need to know whether it exists.
    again = client.post(
        f"/api/v1/projects/{world.project_id}/conversation", headers=auth(world.faculty)
    )
    assert again.json()["id"] == opened.json()["id"]


def test_someone_outside_the_team_cannot_open_it(client: TestClient, world: World) -> None:
    response = client.post(
        f"/api/v1/projects/{world.project_id}/conversation", headers=auth(world.other_student)
    )

    assert response.status_code == 404


def test_joining_a_project_grants_its_thread(client: TestClient, world: World) -> None:
    thread_id = client.post(
        f"/api/v1/projects/{world.project_id}/conversation", headers=auth(world.faculty)
    ).json()["id"]
    _send(client, world.faculty, thread_id, "Team, welcome")

    added = client.post(
        f"/api/v1/projects/{world.project_id}/members",
        headers=auth(world.faculty),
        json={"user_id": str(world.student.id), "member_role": "Research assistant"},
    )
    assert added.status_code in {200, 201}, added.json()

    page = client.get(f"/api/v1/conversations/{thread_id}/messages", headers=auth(world.student))
    assert page.status_code == 200
    assert [item["body"] for item in page.json()["items"]] == ["Team, welcome"]


def test_leaving_a_project_revokes_the_thread_but_keeps_what_was_said(
    client: TestClient, world: World
) -> None:
    """A conversation is a record, not a possession of the current team."""
    thread_id = client.post(
        f"/api/v1/projects/{world.project_id}/conversation", headers=auth(world.faculty)
    ).json()["id"]
    client.post(
        f"/api/v1/projects/{world.project_id}/members",
        headers=auth(world.faculty),
        json={"user_id": str(world.student.id), "member_role": "Research assistant"},
    )
    _send(client, world.student, thread_id, "I ran the calibration")

    removed = client.delete(
        f"/api/v1/projects/{world.project_id}/members/{world.student.id}",
        headers=auth(world.faculty),
    )
    assert removed.status_code in {200, 204}, removed.text

    assert (
        client.get(f"/api/v1/conversations/{thread_id}", headers=auth(world.student)).status_code
        == 404
    ), "access revoked"
    remaining = client.get(
        f"/api/v1/conversations/{thread_id}/messages", headers=auth(world.faculty)
    ).json()
    assert [item["body"] for item in remaining["items"]] == ["I ran the calibration"]


# ---------------------------------------------------------------- deletion


def test_deleting_an_account_reports_its_messages_first(client: TestClient, world: World) -> None:
    thread_id = _accepted_thread(client, world)
    _send(client, world.student, thread_id, "One")
    _send(client, world.student, thread_id, "Two")

    impact = client.get(
        f"/api/v1/users/{world.student.id}/deletion-impact", headers=auth(world.admin)
    ).json()

    assert impact["messages_sent"] == 2
    assert impact["destroys_content"] is True


def test_deleting_the_subject_takes_the_thread_with_it(client: TestClient, world: World) -> None:
    """The reason conversations use real foreign keys and not a polymorphic id:
    a deleted request cannot leave a thread pointing at nothing."""
    thread_id = _accepted_thread(client, world)
    _send(client, world.student, thread_id, "Hello")

    assert (
        client.delete(f"/api/v1/users/{world.student.id}", headers=auth(world.admin)).status_code
        == 204
    )

    assert client.get("/api/v1/me/conversations", headers=auth(world.faculty)).json() == []
