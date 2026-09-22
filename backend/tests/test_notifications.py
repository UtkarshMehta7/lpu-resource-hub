"""Domain events → notifications, per-user isolation, and reminder idempotency."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.jobs.reminders import send_deadline_reminders
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


@pytest.fixture
def session_factory(db_settings: Settings) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(str(db_settings.database_url))
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()


def _notifications(client: TestClient, user: SeededUser) -> dict[str, object]:
    response = client.get("/api/v1/me/notifications", headers=auth(user))
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def _types(body: dict[str, object]) -> list[str]:
    items = body["items"]
    assert isinstance(items, list)
    return [item["notification_type"] for item in items]


def test_application_events_notify_both_sides(client: TestClient, world: World) -> None:
    application_id = client.post(
        f"/api/v1/opportunities/{world.opportunity_id}/applications",
        headers=auth(world.student),
        json={"statement": "I have calibrated sensors before in the field."},
    ).json()["id"]

    # The poster hears about the application...
    poster = _notifications(client, world.faculty)
    assert "application_received" in _types(poster)
    items = poster["items"]
    assert isinstance(items, list)
    assert items[0]["payload"]["opportunity_title"] == "Field assistant for soil sensors"

    # ...and the applicant hears about the decision.
    client.post(
        f"/api/v1/applications/{application_id}/status",
        headers=auth(world.faculty),
        json={"status": "under_review"},
    )
    student = _notifications(client, world.student)
    assert _types(student) == ["application_decided"]
    assert student["unread_count"] == 1


def test_collaboration_and_review_events_notify(client: TestClient, world: World) -> None:
    request_id = client.post(
        "/api/v1/collaborations",
        headers=auth(world.student),
        json={
            "recipient_id": str(world.faculty.id),
            "message": "Could I join the field trials?",
        },
    ).json()["id"]
    assert "collaboration_request" in _types(_notifications(client, world.faculty))

    client.post(f"/api/v1/collaborations/{request_id}/accept", headers=auth(world.faculty))
    assert "collaboration_response" in _types(_notifications(client, world.student))

    # A project review notifies its owner (the fixture's project was approved
    # by the coordinator during setup).
    assert "project_reviewed" in _types(_notifications(client, world.faculty))


def test_booking_decision_notifies_the_requester(client: TestClient, world: World) -> None:
    facility_id = client.post(
        "/api/v1/facilities", headers=auth(world.coordinator), json={"name": "Soil Lab"}
    ).json()["id"]
    equipment_id = client.post(
        "/api/v1/equipment",
        headers=auth(world.coordinator),
        json={"facility_id": facility_id, "name": "Probe", "max_hours": 4},
    ).json()["id"]
    booking_id = client.post(
        "/api/v1/bookings",
        headers=auth(world.student),
        json={
            "equipment_id": equipment_id,
            "starts_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
            "ends_at": (datetime.now(UTC) + timedelta(hours=4)).isoformat(),
            "purpose": "Calibrating the probe.",
        },
    ).json()["id"]
    client.post(f"/api/v1/bookings/{booking_id}/approve", headers=auth(world.coordinator), json={})

    student = _notifications(client, world.student)
    assert "booking_decided" in _types(student)
    items = student["items"]
    assert isinstance(items, list)
    assert items[0]["payload"]["status"] == "approved"


def test_notifications_are_private_and_markable(client: TestClient, world: World) -> None:
    client.post(
        "/api/v1/collaborations",
        headers=auth(world.student),
        json={"recipient_id": str(world.faculty.id), "message": "Can we work together?"},
    )
    before = _notifications(client, world.faculty)
    faculty_items = before["items"]
    assert isinstance(faculty_items, list)
    notification_id = faculty_items[0]["id"]
    unread_before = before["unread_count"]
    assert isinstance(unread_before, int)
    assert unread_before >= 1

    # Someone else's notification is simply not found.
    assert (
        client.post(
            f"/api/v1/me/notifications/{notification_id}/read", headers=auth(world.student)
        ).status_code
        == 404
    )
    assert _notifications(client, world.other_student)["items"] == []

    read = client.post(
        f"/api/v1/me/notifications/{notification_id}/read", headers=auth(world.faculty)
    )
    assert read.status_code == 200
    assert read.json()["read_at"] is not None
    assert _notifications(client, world.faculty)["unread_count"] == unread_before - 1

    # read-all clears the rest, and is then a no-op.
    marked = client.post("/api/v1/me/notifications/read-all", headers=auth(world.faculty)).json()
    assert marked["marked_read"] == unread_before - 1
    assert _notifications(client, world.faculty)["unread_count"] == 0
    assert (
        client.post("/api/v1/me/notifications/read-all", headers=auth(world.faculty)).json()[
            "marked_read"
        ]
        == 0
    )


def test_relevant_opportunity_notification_respects_the_threshold(
    client: TestClient, world: World
) -> None:
    skill_id = client.post(
        "/api/v1/taxonomy/skills", headers=auth(world.coordinator), json={"name": "Sensors"}
    ).json()["id"]
    for name in ("Field Work", "Python"):
        client.post("/api/v1/taxonomy/skills", headers=auth(world.coordinator), json={"name": name})
    skills = client.get("/api/v1/skills", headers=auth(world.student)).json()
    client.put(
        "/api/v1/me/skills",
        headers=auth(world.student),
        json=[{"skill_id": item["id"], "proficiency": 5} for item in skills],
    )

    draft = client.post(
        "/api/v1/opportunities",
        headers=auth(world.faculty),
        json={
            "title": "Sensor calibration assistant",
            "description": "Calibrate soil moisture sensors in the field.",
            "opportunity_type": "research_assistant",
            "project_id": world.project_id,
            "positions": 1,
            "deadline": (datetime.now(UTC).date() + timedelta(days=20)).isoformat(),
            "skills": [{"skill_id": skill_id, "is_required": True}],
        },
    ).json()["id"]
    client.post(f"/api/v1/opportunities/{draft}/publish", headers=auth(world.faculty))

    matched = _notifications(client, world.student)
    assert "relevant_opportunity" in _types(matched)
    items = matched["items"]
    assert isinstance(items, list)
    match = next(item for item in items if item["notification_type"] == "relevant_opportunity")
    assert match["payload"]["reasons"]
    assert match["payload"]["score"] >= 0.35
    # A student with no skills at all is below the threshold, so hears nothing.
    assert "relevant_opportunity" not in _types(_notifications(client, world.other_student))


def test_deadline_reminders_are_sent_once_per_lead_time(
    client: TestClient, world: World, session_factory: sessionmaker[Session]
) -> None:
    in_seven_days = (datetime.now(UTC).date() + timedelta(days=7)).isoformat()
    funding_id = client.post(
        "/api/v1/funding",
        headers=auth(world.coordinator),
        json={
            "organization": "Demo Research Council",
            "title": "Demo seed grant for sensing",
            "description": "A fictional demo funding call.",
            "deadline": in_seven_days,
        },
    ).json()["id"]
    client.post("/api/v1/me/saved", headers=auth(world.student), json={"funding_id": funding_id})

    session = session_factory()
    try:
        assert send_deadline_reminders(session) == 1
        # Running it again -- as the scheduler will, every hour -- adds nothing.
        assert send_deadline_reminders(session) == 0
    finally:
        session.close()

    reminders = [
        item
        for item in _notifications(client, world.student)["items"]  # type: ignore[union-attr]
        if item["notification_type"] == "deadline_reminder"
    ]
    assert len(reminders) == 1
    assert reminders[0]["payload"] == {
        "kind": "funding",
        "item_id": funding_id,
        "title": "Demo seed grant for sensing",
        "days_left": 7,
    }
