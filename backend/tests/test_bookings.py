"""Booking rules, approval workflow and the no-double-booking guarantee.

The headline test is `test_two_overlapping_approvals_cannot_both_succeed`:
two transactions approve overlapping bookings at the same time, and the
database -- not the service -- decides that exactly one wins.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.users.models import CoordinatorScopeType, UserRole
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


@dataclass
class Lab:
    facility_id: str
    equipment_id: str


def _iso(hours_from_now: float) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours_from_now)).isoformat()


@pytest.fixture
def lab(client: TestClient, world: World) -> Lab:
    facility_id = client.post(
        "/api/v1/facilities", headers=auth(world.coordinator), json={"name": "Soil Lab"}
    ).json()["id"]
    equipment_id = client.post(
        "/api/v1/equipment",
        headers=auth(world.coordinator),
        json={
            "facility_id": facility_id,
            "name": "Soil moisture probe",
            "max_hours": 8,
            "min_lead_hours": 0,
        },
    ).json()["id"]
    return Lab(facility_id=facility_id, equipment_id=equipment_id)


def _book(
    client: TestClient, user: SeededUser, equipment_id: str, start: float, end: float
) -> tuple[int, dict[str, object]]:
    response = client.post(
        "/api/v1/bookings",
        headers=auth(user),
        json={
            "equipment_id": equipment_id,
            "starts_at": _iso(start),
            "ends_at": _iso(end),
            "purpose": "Calibrating sensors for the field trial.",
        },
    )
    body: dict[str, object] = response.json()
    return response.status_code, body


def _booking_id(client: TestClient, user: SeededUser, equipment_id: str, s: float, e: float) -> str:
    code, body = _book(client, user, equipment_id, s, e)
    assert code == 201, body
    return str(body["id"])


# --- booking rules ------------------------------------------------------------


def test_booking_rules_are_enforced(client: TestClient, world: World, lab: Lab) -> None:
    assert _book(client, world.student, lab.equipment_id, 2, 4)[0] == 201
    # Longer than max_hours, in the past, or unknown equipment.
    assert _book(client, world.student, lab.equipment_id, 2, 20)[0] == 422
    assert _book(client, world.student, lab.equipment_id, -2, 2)[0] == 422
    assert _book(client, world.student, "00000000-0000-0000-0000-000000000001", 2, 4)[0] == 404
    # ends_at must follow starts_at (one timestamp used for both ends).
    same = _iso(6)
    empty_period = client.post(
        "/api/v1/bookings",
        headers=auth(world.student),
        json={
            "equipment_id": lab.equipment_id,
            "starts_at": same,
            "ends_at": same,
            "purpose": "Zero-length slot.",
        },
    )
    assert empty_period.status_code == 422


def test_students_allowed_and_maintenance_flags(client: TestClient, world: World, lab: Lab) -> None:
    client.patch(
        f"/api/v1/equipment/{lab.equipment_id}",
        headers=auth(world.coordinator),
        json={"students_allowed": False},
    )
    assert _book(client, world.student, lab.equipment_id, 2, 4)[0] == 403
    assert _book(client, world.faculty, lab.equipment_id, 2, 4)[0] == 201

    client.patch(
        f"/api/v1/equipment/{lab.equipment_id}",
        headers=auth(world.coordinator),
        json={"maintenance_status": "maintenance"},
    )
    assert _book(client, world.faculty, lab.equipment_id, 20, 22)[0] == 409


def test_minimum_lead_time(client: TestClient, world: World, lab: Lab) -> None:
    client.patch(
        f"/api/v1/equipment/{lab.equipment_id}",
        headers=auth(world.coordinator),
        json={"min_lead_hours": 24},
    )
    assert _book(client, world.student, lab.equipment_id, 2, 4)[0] == 422
    assert _book(client, world.student, lab.equipment_id, 48, 50)[0] == 201


def test_equipment_without_approval_is_booked_outright(
    client: TestClient, world: World, lab: Lab
) -> None:
    client.patch(
        f"/api/v1/equipment/{lab.equipment_id}",
        headers=auth(world.coordinator),
        json={"requires_approval": False},
    )
    code, body = _book(client, world.student, lab.equipment_id, 2, 4)
    assert code == 201
    assert body["status"] == "approved"
    # ...and the constraint still applies to it.
    assert _book(client, world.other_student, lab.equipment_id, 3, 5)[0] == 409


# --- approval -----------------------------------------------------------------


def test_approval_is_scoped_and_audited(
    client: TestClient, world: World, lab: Lab, seed_user: Callable[..., SeededUser]
) -> None:
    booking_id = _booking_id(client, world.student, lab.equipment_id, 2, 4)

    assert (
        client.get("/api/v1/coordinator/booking-queue", headers=auth(world.student)).status_code
        == 403
    )
    queue = client.get("/api/v1/coordinator/booking-queue", headers=auth(world.coordinator))
    assert [item["id"] for item in queue.json()] == [booking_id]

    # A coordinator from another department sees neither the queue entry nor
    # the booking itself.
    school_id = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Science School"}
    ).json()["id"]
    other_department = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": school_id, "name": "Chemistry"},
    ).json()["id"]
    outsider = seed_user(
        UserRole.RESEARCH_COORDINATOR,
        department_id=other_department,
        coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
        coordinator_scope_id=other_department,
    )
    assert client.get("/api/v1/coordinator/booking-queue", headers=auth(outsider)).json() == []
    assert (
        client.post(
            f"/api/v1/bookings/{booking_id}/approve", headers=auth(outsider), json={}
        ).status_code
        == 404
    )
    # The owner can't approve their own request.
    assert (
        client.post(
            f"/api/v1/bookings/{booking_id}/approve", headers=auth(world.student), json={}
        ).status_code
        == 403
    )

    approved = client.post(
        f"/api/v1/bookings/{booking_id}/approve",
        headers=auth(world.coordinator),
        json={"note": "Booked for the field trial."},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["decided_by"] == str(world.coordinator.id)
    assert (
        client.post(
            f"/api/v1/bookings/{booking_id}/reject", headers=auth(world.coordinator), json={}
        ).status_code
        == 409
    )
    logs = client.get("/api/v1/admin/audit-logs", headers=auth(world.admin)).json()["items"]
    assert any(log["action"] == "booking.approved" for log in logs)


def test_pending_requests_may_overlap_but_only_one_is_approved(
    client: TestClient, world: World, lab: Lab
) -> None:
    first = _booking_id(client, world.student, lab.equipment_id, 2, 4)
    second = _booking_id(client, world.other_student, lab.equipment_id, 3, 5)

    assert (
        client.post(
            f"/api/v1/bookings/{first}/approve", headers=auth(world.coordinator), json={}
        ).status_code
        == 200
    )
    conflict = client.post(
        f"/api/v1/bookings/{second}/approve", headers=auth(world.coordinator), json={}
    )
    assert conflict.status_code == 409
    assert "already taken" in conflict.json()["error"]["message"]

    # Back-to-back slots don't overlap: [2,4) and [4,6) both fit.
    third = _booking_id(client, world.other_student, lab.equipment_id, 4, 6)
    assert (
        client.post(
            f"/api/v1/bookings/{third}/approve", headers=auth(world.coordinator), json={}
        ).status_code
        == 200
    )


def test_two_overlapping_approvals_cannot_both_succeed(
    client: TestClient, world: World, lab: Lab, db_settings: Settings
) -> None:
    """Two transactions approve overlapping bookings at the same moment.

    Nothing in the service checks for overlap; the EXCLUDE constraint is the
    only arbiter, so exactly one commit survives.
    """
    first = _booking_id(client, world.student, lab.equipment_id, 2, 4)
    second = _booking_id(client, world.other_student, lab.equipment_id, 3, 5)

    engine = create_engine(str(db_settings.database_url))
    session_factory = sessionmaker(bind=engine)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def approve(booking_id: str, *, flush_first: bool) -> None:
        """Both transactions are open at once and both try to approve.

        The first writes its row and holds it; the second then runs straight
        into the exclusion constraint and has to wait for the first to commit
        before PostgreSQL can tell it the slot is gone. (Flushing both before
        the barrier would have them wait on each other instead -- a deadlock,
        which the server also resolves, but less informatively.)
        """
        session: Session = session_factory()
        outcome = "conflict"
        try:
            booking = session.get(Booking, booking_id)
            assert booking is not None
            booking.status = BookingStatus.APPROVED
            if flush_first:
                session.flush()
                barrier.wait(timeout=10)
            else:
                barrier.wait(timeout=10)
                session.flush()
            session.commit()
            outcome = "approved"
        except (IntegrityError, OperationalError):
            session.rollback()
        finally:
            session.close()
        with lock:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=approve, args=(first,), kwargs={"flush_first": True}),
        threading.Thread(target=approve, args=(second,), kwargs={"flush_first": False}),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    engine.dispose()

    assert sorted(outcomes) == ["approved", "conflict"]
    approved = client.get("/api/v1/me/bookings", headers=auth(world.student)).json()
    other = client.get("/api/v1/me/bookings", headers=auth(world.other_student)).json()
    statuses = [booking["status"] for booking in approved + other]
    assert statuses.count("approved") == 1


# --- cancelling and completing ------------------------------------------------


def test_cancel_only_before_start(
    client: TestClient, world: World, lab: Lab, db_settings: Settings
) -> None:
    booking_id = _booking_id(client, world.student, lab.equipment_id, 2, 4)
    assert (
        client.post(
            f"/api/v1/bookings/{booking_id}/approve", headers=auth(world.coordinator), json={}
        ).status_code
        == 200
    )
    # Someone unrelated can't even see it.
    assert (
        client.post(
            f"/api/v1/bookings/{booking_id}/cancel", headers=auth(world.faculty)
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/bookings/{booking_id}/cancel", headers=auth(world.student)
        ).status_code
        == 200
    )

    # A booking that has already started can't be cancelled.
    started = _booking_id(client, world.student, lab.equipment_id, 6, 8)
    engine = create_engine(str(db_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE bookings SET period = tstzrange(now() - interval '1 hour', "
                    "now() + interval '1 hour', '[)') WHERE id = :id"
                ),
                {"id": started},
            )
    finally:
        engine.dispose()
    assert (
        client.post(f"/api/v1/bookings/{started}/cancel", headers=auth(world.student)).status_code
        == 409
    )


def test_completing_needs_the_booking_to_be_over(
    client: TestClient, world: World, lab: Lab, db_settings: Settings
) -> None:
    booking_id = _booking_id(client, world.student, lab.equipment_id, 2, 4)
    client.post(f"/api/v1/bookings/{booking_id}/approve", headers=auth(world.coordinator), json={})
    assert (
        client.post(
            f"/api/v1/bookings/{booking_id}/complete", headers=auth(world.student)
        ).status_code
        == 409
    )
    engine = create_engine(str(db_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE bookings SET period = tstzrange(now() - interval '3 hours', "
                    "now() - interval '1 hour', '[)') WHERE id = :id"
                ),
                {"id": booking_id},
            )
    finally:
        engine.dispose()
    completed = client.post(f"/api/v1/bookings/{booking_id}/complete", headers=auth(world.student))
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"


# --- availability -------------------------------------------------------------


def test_availability_shows_periods_without_naming_the_booker(
    client: TestClient, world: World, lab: Lab
) -> None:
    booking_id = _booking_id(client, world.student, lab.equipment_id, 2, 4)
    client.post(f"/api/v1/bookings/{booking_id}/approve", headers=auth(world.coordinator), json={})
    pending = _booking_id(client, world.other_student, lab.equipment_id, 10, 12)
    assert pending

    def availability(user: SeededUser) -> dict[str, object]:
        response = client.get(
            f"/api/v1/equipment/{lab.equipment_id}/availability",
            headers=auth(user),
            params={"from": _iso(0), "to": _iso(48)},
        )
        assert response.status_code == 200, response.text
        body: dict[str, object] = response.json()
        return body

    mine = availability(world.student)
    assert len(mine["busy"]) == 1  # only approved bookings block a slot
    assert mine["busy"][0]["is_mine"] is True
    assert mine["max_hours"] == 8

    theirs = availability(world.other_student)
    assert theirs["busy"][0]["is_mine"] is False
    assert "user_name" not in theirs["busy"][0]
