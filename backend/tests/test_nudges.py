"""Nudging whoever has to act next.

The rules worth pinning are the ones that stop this becoming a way to spam
somebody senior: you may only chase your own thing, only while it is really
waiting, and only once a day.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.modules.notifications.models import Notification, NotificationType
from app.modules.users.models import UserRole
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


def nudge(client: TestClient, user: SeededUser, kind: str, entity_id: str):
    return client.post(
        "/api/v1/nudges", headers=auth(user), json={"kind": kind, "entity_id": entity_id}
    )


def notifications_of(db_settings: Settings, kind: NotificationType) -> list[Notification]:
    engine = create_engine(str(db_settings.database_url))
    try:
        with sessionmaker(bind=engine)() as db:
            return list(
                db.scalars(select(Notification).where(Notification.notification_type == kind)).all()
            )
    finally:
        engine.dispose()


# --- profile verification --------------------------------------------------


def test_a_pending_profile_can_be_chased(
    client: TestClient, world: World, db_settings: Settings, seed_user: Callable[..., SeededUser]
) -> None:
    waiting = seed_user(UserRole.FACULTY, department_id=world.department_id)
    client.put(
        "/api/v1/me/profile",
        headers=auth(waiting),
        json={"designation": "Professor", "bio": "Waiting on verification."},
    )
    response = nudge(client, waiting, "profile_verification", str(waiting.id))
    assert response.status_code == 201
    body = response.json()
    assert body["recipients"] >= 1

    told = notifications_of(db_settings, NotificationType.NUDGE_RECEIVED)
    assert len(told) == body["recipients"]
    # It reaches the department's coordinator, not everybody.
    assert {n.user_id for n in told} == {world.coordinator.id}


def test_an_already_verified_profile_has_nothing_to_chase(client: TestClient, world: World) -> None:
    response = nudge(client, world.faculty, "profile_verification", str(world.faculty.id))
    assert response.status_code == 404


def test_you_cannot_chase_somebody_elses_profile(client: TestClient, world: World) -> None:
    response = nudge(client, world.student, "profile_verification", str(world.faculty.id))
    assert response.status_code == 404


# --- cooldown --------------------------------------------------------------


def test_the_same_thing_can_only_be_chased_once_a_day(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    waiting = seed_user(UserRole.FACULTY, department_id=world.department_id)
    client.put(
        "/api/v1/me/profile",
        headers=auth(waiting),
        json={"designation": "Professor", "bio": "Waiting."},
    )
    assert nudge(client, waiting, "profile_verification", str(waiting.id)).status_code == 201
    again = nudge(client, waiting, "profile_verification", str(waiting.id))
    assert again.status_code == 429
    assert "again after" in again.json()["error"]["message"]


def test_the_cooldown_lifts(
    client: TestClient,
    world: World,
    db_settings: Settings,
    seed_user: Callable[..., SeededUser],
) -> None:
    waiting = seed_user(UserRole.FACULTY, department_id=world.department_id)
    client.put(
        "/api/v1/me/profile",
        headers=auth(waiting),
        json={"designation": "Professor", "bio": "Waiting."},
    )
    nudge(client, waiting, "profile_verification", str(waiting.id))

    # Age the record rather than waiting a day.
    engine = create_engine(str(db_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE nudges SET created_at = :then"),
                {"then": datetime.now(UTC) - timedelta(hours=25)},
            )
    finally:
        engine.dispose()

    assert nudge(client, waiting, "profile_verification", str(waiting.id)).status_code == 201


# --- projects --------------------------------------------------------------


def test_a_project_awaiting_review_can_be_chased(client: TestClient, world: World) -> None:
    project_id = client.post(
        "/api/v1/projects",
        headers=auth(world.faculty),
        json={"title": "Pending work", "summary": "S", "description": "D"},
    ).json()["id"]
    client.post(f"/api/v1/projects/{project_id}/submit", headers=auth(world.faculty))

    assert nudge(client, world.faculty, "project_review", project_id).status_code == 201


def test_an_approved_project_has_nothing_to_chase(client: TestClient, world: World) -> None:
    assert nudge(client, world.faculty, "project_review", world.project_id).status_code == 404


def test_you_cannot_chase_review_of_a_project_that_is_not_yours(
    client: TestClient, world: World
) -> None:
    assert nudge(client, world.student, "project_review", world.project_id).status_code == 404


# --- shape -----------------------------------------------------------------


def test_signing_in_is_required(client: TestClient) -> None:
    response = client.post(
        "/api/v1/nudges",
        json={"kind": "profile_verification", "entity_id": str(uuid.uuid4())},
    )
    assert response.status_code == 401


def test_an_unknown_thing_is_a_404_not_a_500(client: TestClient, world: World) -> None:
    assert nudge(client, world.faculty, "project_review", str(uuid.uuid4())).status_code == 404


def test_the_sender_never_chooses_the_recipient(client: TestClient) -> None:
    """There is deliberately no recipient field -- it would be a way to
    message anybody in the institution."""
    schema = client.get("/openapi.json").json()["components"]["schemas"]["NudgeRequest"]
    assert set(schema["properties"]) == {"kind", "entity_id"}


# --- a dean escalating, which is the only nudge that travels downward ------


def _slipping_project(client: TestClient, world: World) -> str:
    """A project with a milestone already past its date."""
    project_id = world.project_id
    created = client.post(
        f"/api/v1/projects/{project_id}/milestones",
        headers=auth(world.faculty),
        json={
            "title": "Field work",
            "due_date": (datetime.now(UTC).date() - timedelta(days=5)).isoformat(),
        },
    )
    assert created.status_code in (200, 201), created.text
    return project_id


def test_a_dean_asks_the_coordinator_to_look_at_a_slipping_project(
    client: TestClient,
    world: World,
    db_settings: Settings,
    seed_user: Callable[..., SeededUser],
) -> None:
    """The dean can act on what they see without editing any of it.

    Every other nudge is "my own thing is stuck"; this one is an institutional
    reader saying "somebody else's is slipping". It reaches the department's
    coordinator, which is who can actually do something.
    """
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)
    project_id = _slipping_project(client, world)

    response = nudge(client, dean, "project_at_risk", project_id)

    assert response.status_code == 201, response.text
    assert response.json()["recipients"] >= 1
    told = notifications_of(db_settings, NotificationType.NUDGE_RECEIVED)
    assert {n.user_id for n in told} == {world.coordinator.id}


def test_a_healthy_project_cannot_be_escalated(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """ "Please look at this" about a project that is perfectly on track is
    noise, and somebody who gets one such nudge discounts the next."""
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)
    healthy = client.post(
        f"/api/v1/projects/{world.project_id}/milestones",
        headers=auth(world.faculty),
        json={
            "title": "Comfortably ahead",
            "due_date": (datetime.now(UTC).date() + timedelta(days=200)).isoformat(),
        },
    )
    assert healthy.status_code in (200, 201), healthy.text

    response = nudge(client, dean, "project_at_risk", world.project_id)

    assert response.status_code == 404, response.text


def test_a_project_with_no_milestones_cannot_be_escalated(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)

    response = nudge(client, dean, "project_at_risk", world.project_id)

    assert response.status_code == 404, response.text


@pytest.mark.parametrize(
    "role", [UserRole.FACULTY, UserRole.STUDENT, UserRole.RESEARCH_COORDINATOR]
)
def test_only_an_institution_wide_reader_may_escalate(
    client: TestClient,
    world: World,
    seed_user: Callable[..., SeededUser],
    role: UserRole,
) -> None:
    """A coordinator escalating would be nudging themselves, and an owner
    already has PROJECT_REVIEW for their own work."""
    person = seed_user(role, department_id=world.department_id)
    project_id = _slipping_project(client, world)

    response = nudge(client, person, "project_at_risk", project_id)

    assert response.status_code == 404, response.text


def test_the_escalation_still_names_no_recipient(client: TestClient, world: World) -> None:
    """The request is a kind and an entity, exactly as for every other nudge.

    A recipient field would turn this into a way to message anybody in the
    institution, which is the whole reason the service resolves recipients
    from the thing being chased.
    """
    from app.modules.nudges.schemas import NudgeRequest

    assert set(NudgeRequest.model_fields) == {"kind", "entity_id"}
