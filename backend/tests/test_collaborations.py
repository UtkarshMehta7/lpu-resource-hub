"""Collaboration request workflow, privacy and rate limiting (real PostgreSQL)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.rate_limit import COLLABORATION_RATE_LIMIT_MAX_REQUESTS
from app.main import create_app
from app.modules.users.models import UserRole
from tests.conftest import SeededUser

pytestmark = pytest.mark.db

UNKNOWN_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


def _auth(user: SeededUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.access_token}"}


@dataclass
class World:
    admin: SeededUser
    faculty: SeededUser
    other_faculty: SeededUser
    coordinator: SeededUser
    student: SeededUser  # opted in to discovery
    private_student: SeededUser  # has a profile, not discoverable
    unprofiled_student: SeededUser  # no profile at all


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    def student(discoverable: bool | None) -> SeededUser:
        user = seed_user(UserRole.STUDENT)
        if discoverable is not None:
            response = client.put(
                "/api/v1/me/profile",
                headers=_auth(user),
                json={"program": "B.Tech", "year": 2, "is_discoverable": discoverable},
            )
            assert response.status_code == 200, response.text
        return user

    return World(
        admin=seed_user(UserRole.ADMIN),
        faculty=seed_user(UserRole.FACULTY),
        other_faculty=seed_user(UserRole.FACULTY),
        coordinator=seed_user(UserRole.RESEARCH_COORDINATOR),
        student=student(True),
        private_student=student(False),
        unprofiled_student=student(None),
    )


def _send(
    client: TestClient, sender: SeededUser, recipient_id: object, **extra: object
) -> tuple[int, dict[str, object]]:
    response = client.post(
        "/api/v1/collaborations",
        headers=_auth(sender),
        json={"recipient_id": str(recipient_id), "message": "Shall we work together?", **extra},
    )
    body: dict[str, object] = response.json()
    return response.status_code, body


def _request_id(client: TestClient, sender: SeededUser, recipient: SeededUser) -> str:
    code, body = _send(client, sender, recipient.id)
    assert code == 201, body
    return str(body["id"])


def _act(client: TestClient, user: SeededUser, request_id: str, action: str) -> int:
    return client.post(
        f"/api/v1/collaborations/{request_id}/{action}", headers=_auth(user)
    ).status_code


# --- privacy / who may contact whom -------------------------------------------


@pytest.mark.parametrize(
    ("sender", "recipient", "expected"),
    [
        ("student", "faculty", 201),
        ("student", "coordinator", 201),
        ("private_student", "student", 201),  # opted-in students are reachable
        ("student", "private_student", 404),
        ("faculty", "private_student", 404),
        ("faculty", "unprofiled_student", 404),
        ("faculty", "student", 201),
        ("faculty", "other_faculty", 201),
        ("coordinator", "faculty", 201),
        ("faculty", "admin", 404),
        ("admin", "faculty", 403),  # admins can't send
    ],
)
def test_who_may_contact_whom(
    client: TestClient, world: World, sender: str, recipient: str, expected: int
) -> None:
    code, _ = _send(client, getattr(world, sender), getattr(world, recipient).id)
    assert code == expected


def test_self_unknown_and_inactive_recipients(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    assert _send(client, world.faculty, world.faculty.id)[0] == 422
    assert _send(client, world.faculty, UNKNOWN_ID)[0] == 404
    inactive = seed_user(UserRole.FACULTY, is_active=False)
    assert _send(client, world.faculty, inactive.id)[0] == 404


def test_db_rejects_a_pair_with_itself(
    client: TestClient, world: World, db_settings: Settings
) -> None:
    """Nobody collaborates with themselves, and the database says so.

    This used to insert a self-addressed request directly. Requests now carry
    a NOT NULL collaboration_id, so that insert would raise for the wrong
    reason and prove nothing. The guarantee moved up to the pair: user_a_id <
    user_b_id cannot hold when they are the same person.
    """
    engine = create_engine(str(db_settings.database_url))
    try:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text("INSERT INTO collaborations (user_a_id, user_b_id) VALUES (:u, :u)"),
                {"u": str(world.faculty.id)},
            )
    finally:
        engine.dispose()


def test_only_parties_can_see_a_request(client: TestClient, world: World) -> None:
    request_id = _request_id(client, world.student, world.faculty)
    url = f"/api/v1/collaborations/{request_id}"
    assert client.get(url, headers=_auth(world.student)).status_code == 200
    assert client.get(url, headers=_auth(world.faculty)).status_code == 200
    assert client.get(url, headers=_auth(world.other_faculty)).status_code == 404
    assert client.get(url, headers=_auth(world.admin)).status_code == 404
    assert _act(client, world.other_faculty, request_id, "accept") == 404


# --- workflow ------------------------------------------------------------------


def test_only_recipient_responds(client: TestClient, world: World) -> None:
    request_id = _request_id(client, world.student, world.faculty)
    assert _act(client, world.student, request_id, "accept") == 403
    assert _act(client, world.student, request_id, "decline") == 403
    assert _act(client, world.faculty, request_id, "accept") == 200
    assert _act(client, world.faculty, request_id, "decline") == 409
    assert _act(client, world.student, request_id, "cancel") == 409
    body = client.get(f"/api/v1/collaborations/{request_id}", headers=_auth(world.student)).json()
    assert body["status"] == "accepted"
    assert body["responded_at"] is not None


def test_only_sender_cancels(client: TestClient, world: World) -> None:
    request_id = _request_id(client, world.student, world.faculty)
    assert _act(client, world.faculty, request_id, "cancel") == 403
    assert _act(client, world.student, request_id, "cancel") == 200
    assert _act(client, world.faculty, request_id, "accept") == 409


def test_one_live_relationship_per_pair(client: TestClient, world: World) -> None:
    """The pair is one row, so there is one answer to "are we collaborating?".

    This used to be three separate yeses: a second request in the same
    direction was refused, but the reverse direction was allowed, and a
    project-scoped request was allowed alongside a general one -- so two
    people could end up with three live requests and, once accepted, three
    conversations (ADR 0023).
    """
    first = _request_id(client, world.faculty, world.other_faculty)

    assert _send(client, world.faculty, world.other_faculty.id)[0] == 409, "same direction"
    assert _send(client, world.other_faculty, world.faculty.id)[0] == 409, "reverse direction"

    project_id = client.post(
        "/api/v1/projects",
        headers=_auth(world.faculty),
        json={"title": "Private draft", "summary": "S", "description": "D"},
    ).json()["id"]
    code, _ = _send(client, world.faculty, world.other_faculty.id, project_id=project_id)
    assert code == 409, "a project does not buy a second relationship"

    # Once answered, there is no relationship, so either may ask again.
    assert _act(client, world.other_faculty, first, "decline") == 200
    assert _send(client, world.faculty, world.other_faculty.id)[0] == 201


def test_a_project_scoped_request_still_carries_the_project(
    client: TestClient, world: World
) -> None:
    """Keeping the pair as the relationship does not lose the project a
    request is about -- nor show a draft to somebody who can't see it."""
    project_id = client.post(
        "/api/v1/projects",
        headers=_auth(world.faculty),
        json={"title": "Private draft", "summary": "S", "description": "D"},
    ).json()["id"]

    code, body = _send(client, world.faculty, world.other_faculty.id, project_id=project_id)

    assert code == 201
    assert body["project_title"] == "Private draft", "the sender can see it"
    received = client.get(
        f"/api/v1/collaborations/{body['id']}", headers=_auth(world.other_faculty)
    ).json()
    assert received["project_title"] is None, "the recipient cannot see the draft"


def test_cannot_reference_a_project_you_cannot_see(client: TestClient, world: World) -> None:
    project_id = client.post(
        "/api/v1/projects",
        headers=_auth(world.faculty),
        json={"title": "Private draft", "summary": "S", "description": "D"},
    ).json()["id"]
    code, _ = _send(client, world.student, world.faculty.id, project_id=project_id)
    assert code == 404


def test_inbox_and_sent(client: TestClient, world: World) -> None:
    _request_id(client, world.student, world.faculty)
    declined = _request_id(client, world.other_faculty, world.faculty)
    _act(client, world.faculty, declined, "decline")

    def box(user: SeededUser, name: str, **params: str) -> list[str]:
        response = client.get(
            "/api/v1/me/collaborations", headers=_auth(user), params={"box": name, **params}
        )
        return [r["sender"]["full_name"] for r in response.json()]

    assert len(box(world.faculty, "inbox")) == 2
    assert len(box(world.faculty, "inbox", status="pending")) == 1
    assert box(world.faculty, "sent") == []
    assert len(box(world.student, "sent")) == 1
    assert box(world.student, "inbox") == []


def test_sending_is_rate_limited_per_user(client: TestClient, world: World) -> None:
    for _ in range(COLLABORATION_RATE_LIMIT_MAX_REQUESTS):
        assert _send(client, world.faculty, UNKNOWN_ID)[0] == 404
    assert _send(client, world.faculty, world.other_faculty.id)[0] == 429
    # Another user's budget is untouched.
    assert _send(client, world.other_faculty, world.faculty.id)[0] == 201
