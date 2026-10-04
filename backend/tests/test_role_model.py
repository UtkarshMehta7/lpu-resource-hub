"""The two roles the specification names that this platform lacked.

A facility custodian looks after the facilities assigned to them. A dean of
research reads institutional figures and changes nothing. Both are tested
against the API directly rather than through the interface, because hiding a
menu item is not a permission.

The case that matters most is `test_a_custodian_cannot_touch_another
_custodians_facility`: before `facilities.custodian_id` existed, holding
FACILITY_MANAGE meant holding it over *every* facility.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.core.permissions import (
    APPOINTABLE_BY_ADMIN,
    DELETABLE_ROLES,
    ROLE_PERMISSIONS,
    Permission,
)
from app.main import create_app
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


def make_facility(client: TestClient, world: World, name: str) -> str:
    created = client.post("/api/v1/facilities", headers=auth(world.admin), json={"name": name})
    assert created.status_code in (200, 201), created.text
    facility_id: str = created.json()["id"]
    return facility_id


def assign_custodian(db_settings: Settings, facility_id: str, user_id: object) -> None:
    """Assigned directly: the appointment endpoint is Phase 6's business."""
    engine = create_engine(str(db_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE facilities SET custodian_id = :u WHERE id = :f"),
                {"u": user_id, "f": facility_id},
            )
    finally:
        engine.dispose()


# --- the permission tables themselves --------------------------------------


def test_a_custodian_holds_only_facility_powers() -> None:
    held = ROLE_PERMISSIONS[UserRole.FACILITY_CUSTODIAN]
    assert held == {Permission.FACILITY_MANAGE, Permission.BOOKING_APPROVE}
    # Emphatically not: they look after rooms, not people or research.
    for forbidden in (
        Permission.USER_CREATE,
        Permission.PROFILE_VERIFY,
        Permission.PROJECT_REVIEW,
        Permission.ANALYTICS_READ,
        Permission.TAXONOMY_MANAGE,
    ):
        assert forbidden not in held


def test_a_dean_reads_and_changes_nothing() -> None:
    held = ROLE_PERMISSIONS[UserRole.DEAN_OF_RESEARCH]
    assert held == {Permission.ANALYTICS_READ}


def test_neither_new_role_can_remove_anybody() -> None:
    assert DELETABLE_ROLES[UserRole.FACILITY_CUSTODIAN] == frozenset()
    assert DELETABLE_ROLES[UserRole.DEAN_OF_RESEARCH] == frozenset()


def test_an_administrator_still_cannot_appoint_another_administrator() -> None:
    """Promotion to admin is the two-person ceremony, not a form field."""
    assert UserRole.ADMIN not in APPOINTABLE_BY_ADMIN
    assert UserRole.FACILITY_CUSTODIAN in APPOINTABLE_BY_ADMIN
    assert UserRole.DEAN_OF_RESEARCH in APPOINTABLE_BY_ADMIN


# --- appointing them -------------------------------------------------------


def appoint(client: TestClient, world: World, role: str, **extra: object) -> dict[str, object]:
    response = client.post(
        "/api/v1/admin/users",
        headers=auth(world.admin),
        json={
            "registration_number": f"T{role[:4].upper()}{datetime.now(UTC).strftime('%f')}",
            "full_name": f"A {role}",
            "role": role,
            **extra,
        },
    )
    assert response.status_code in (200, 201), response.text
    # The response nests the account under "user" alongside the one-time
    # temporary password.
    body: dict[str, object] = response.json()["user"]
    return body


def test_an_administrator_appoints_a_custodian_and_a_dean(client: TestClient, world: World) -> None:
    custodian = appoint(client, world, "facility_custodian", department_id=world.department_id)
    assert custodian["role"] == "facility_custodian"
    # A dean answers to the institution, so needs no department.
    dean = appoint(client, world, "dean_of_research")
    assert dean["role"] == "dean_of_research"


def test_an_administrator_cannot_mint_an_administrator_through_the_override(
    client: TestClient, world: World
) -> None:
    response = client.post(
        "/api/v1/admin/users",
        headers=auth(world.admin),
        json={
            "registration_number": "TNEWADMIN01",
            "full_name": "Would-be admin",
            "role": "admin",
        },
    )
    assert response.status_code == 403


def test_a_coordinator_cannot_appoint_a_custodian(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/admin/users",
        headers=auth(world.coordinator),
        json={
            "registration_number": "TSNEAK0001",
            "full_name": "Sneaky",
            "role": "facility_custodian",
        },
    )
    assert response.status_code == 403


# --- the custodian's scope, which is the point of the role -----------------


def test_a_custodian_cannot_touch_another_custodians_facility(
    client: TestClient,
    world: World,
    db_settings: Settings,
    seed_user: Callable[..., SeededUser],
) -> None:
    """The hole this role closes.

    Before facilities.custodian_id existed, FACILITY_MANAGE meant holding it
    over every facility in the institution.
    """
    mine = make_facility(client, world, "Soil Lab")
    theirs = make_facility(client, world, "Electron Microscopy Suite")

    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)
    assign_custodian(db_settings, mine, custodian.id)

    allowed = client.patch(
        f"/api/v1/facilities/{mine}", headers=auth(custodian), json={"location": "Block 7"}
    )
    assert allowed.status_code == 200, allowed.text

    refused = client.patch(
        f"/api/v1/facilities/{theirs}", headers=auth(custodian), json={"location": "Block 7"}
    )
    assert refused.status_code in (403, 404), refused.text


def test_a_custodian_with_no_facility_manages_nothing(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    facility = make_facility(client, world, "Unassigned Lab")
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)
    response = client.patch(
        f"/api/v1/facilities/{facility}", headers=auth(custodian), json={"location": "X"}
    )
    assert response.status_code in (403, 404)


def test_equipment_inherits_its_facilitys_custodian(
    client: TestClient,
    world: World,
    db_settings: Settings,
    seed_user: Callable[..., SeededUser],
) -> None:
    """Whoever looks after the room looks after what is in it."""
    mine = make_facility(client, world, "My Lab")
    theirs = make_facility(client, world, "Their Lab")
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)
    assign_custodian(db_settings, mine, custodian.id)

    ours = client.post(
        "/api/v1/equipment",
        headers=auth(world.admin),
        json={"facility_id": mine, "name": "Spectrometer"},
    ).json()["id"]
    not_ours = client.post(
        "/api/v1/equipment",
        headers=auth(world.admin),
        json={"facility_id": theirs, "name": "Microscope"},
    ).json()["id"]

    assert (
        client.patch(
            f"/api/v1/equipment/{ours}", headers=auth(custodian), json={"category": "Optics"}
        ).status_code
        == 200
    )
    assert client.patch(
        f"/api/v1/equipment/{not_ours}", headers=auth(custodian), json={"category": "Optics"}
    ).status_code in (403, 404)


def test_a_custodian_approves_only_bookings_in_their_own_facility(
    client: TestClient,
    world: World,
    db_settings: Settings,
    seed_user: Callable[..., SeededUser],
) -> None:
    mine = make_facility(client, world, "Bookable Lab")
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)
    assign_custodian(db_settings, mine, custodian.id)
    equipment = client.post(
        "/api/v1/equipment",
        headers=auth(world.admin),
        json={"facility_id": mine, "name": "Centrifuge", "requires_approval": True},
    ).json()["id"]

    starts = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    ends = (datetime.now(UTC) + timedelta(days=1, hours=2)).isoformat()
    booking = client.post(
        "/api/v1/bookings",
        headers=auth(world.faculty),
        json={
            "equipment_id": equipment,
            "starts_at": starts,
            "ends_at": ends,
            "purpose": "Sample preparation.",
        },
    )
    assert booking.status_code in (200, 201), booking.text
    booking_id = booking.json()["id"]

    approved = client.post(
        f"/api/v1/bookings/{booking_id}/approve", headers=auth(custodian), json={}
    )
    assert approved.status_code == 200, approved.text


def test_a_custodian_is_a_stranger_to_a_booking_elsewhere(
    client: TestClient,
    world: World,
    db_settings: Settings,
    seed_user: Callable[..., SeededUser],
) -> None:
    mine = make_facility(client, world, "Mine")
    theirs = make_facility(client, world, "Theirs")
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)
    assign_custodian(db_settings, mine, custodian.id)
    equipment = client.post(
        "/api/v1/equipment",
        headers=auth(world.admin),
        json={"facility_id": theirs, "name": "Furnace", "requires_approval": True},
    ).json()["id"]

    starts = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    ends = (datetime.now(UTC) + timedelta(days=2, hours=1)).isoformat()
    booking_id = client.post(
        "/api/v1/bookings",
        headers=auth(world.faculty),
        json={
            "equipment_id": equipment,
            "starts_at": starts,
            "ends_at": ends,
            "purpose": "Firing samples.",
        },
    ).json()["id"]

    # 404, not 403: a custodian should not learn which bookings exist
    # elsewhere by being refused them.
    response = client.post(
        f"/api/v1/bookings/{booking_id}/approve", headers=auth(custodian), json={}
    )
    assert response.status_code == 404


def test_the_booking_queue_shows_a_custodian_exactly_what_they_may_approve(
    client: TestClient,
    world: World,
    db_settings: Settings,
    seed_user: Callable[..., SeededUser],
) -> None:
    """The queue and the approve call must agree.

    They are two code paths over the same rule -- a filtered query and an
    object-level check -- so a listing that showed a request the approve call
    then refused would be a dead button, and one that hid a request the
    custodian is responsible for would leave it waiting for nobody.
    """
    mine = make_facility(client, world, "Mine")
    theirs = make_facility(client, world, "Theirs")
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)
    assign_custodian(db_settings, mine, custodian.id)

    wanted: list[str] = []
    for index, (facility, name) in enumerate(((mine, "Centrifuge"), (theirs, "Furnace"))):
        equipment = client.post(
            "/api/v1/equipment",
            headers=auth(world.admin),
            json={"facility_id": facility, "name": name, "requires_approval": True},
        ).json()["id"]
        starts = datetime.now(UTC) + timedelta(days=3 + index)
        booking_id = client.post(
            "/api/v1/bookings",
            headers=auth(world.faculty),
            json={
                "equipment_id": equipment,
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(hours=1)).isoformat(),
                "purpose": "Sample preparation.",
            },
        ).json()["id"]
        if facility == mine:
            wanted.append(booking_id)

    queue = client.get("/api/v1/coordinator/booking-queue", headers=auth(custodian))
    assert queue.status_code == 200, queue.text
    assert [row["id"] for row in queue.json()] == wanted

    # And every row it offered really is approvable.
    for booking_id in wanted:
        approved = client.post(
            f"/api/v1/bookings/{booking_id}/approve", headers=auth(custodian), json={}
        )
        assert approved.status_code == 200, approved.text


def test_a_custodian_with_no_facility_has_an_empty_booking_queue(
    client: TestClient,
    world: World,
    seed_user: Callable[..., SeededUser],
) -> None:
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)

    queue = client.get("/api/v1/coordinator/booking-queue", headers=auth(custodian))

    # Empty, not refused: they hold the permission, they just hold no rooms.
    assert queue.status_code == 200
    assert queue.json() == []


# --- the dean's reach ------------------------------------------------------


def test_a_dean_reads_institutional_analytics(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)
    for path in (
        "/api/v1/analytics/overview",
        "/api/v1/analytics/institutional-report",
        "/api/v1/coordinator/at-risk-projects",
    ):
        response = client.get(path, headers=auth(dean))
        assert response.status_code == 200, f"{path}: {response.text}"


def test_a_deans_figures_cover_the_whole_institution(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """Not one department -- that is the difference from a coordinator."""
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)
    report = client.get("/api/v1/analytics/institutional-report", headers=auth(dean)).json()
    assert report["scope"] == "the whole institution"


def test_a_dean_changes_nothing(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """Read-only is the role. Each of these would be a different job."""
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)
    refusals = [
        client.post(
            "/api/v1/admin/users",
            headers=auth(dean),
            json={"registration_number": "TX01", "full_name": "X", "role": "faculty"},
        ),
        client.post(
            f"/api/v1/researchers/{world.other_faculty.id}/verify",
            headers=auth(dean),
            json={"decision": "verified"},
        ),
        client.post("/api/v1/facilities", headers=auth(dean), json={"name": "Dean's Lab"}),
        client.post(
            f"/api/v1/projects/{world.project_id}/review",
            headers=auth(dean),
            json={"decision": "approve"},
        ),
    ]
    assert [r.status_code for r in refusals] == [403, 403, 403, 403]


def test_a_custodian_cannot_read_institutional_analytics(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)
    assert (
        client.get("/api/v1/analytics/institutional-report", headers=auth(custodian)).status_code
        == 403
    )


def test_neither_new_role_uses_the_administrator_entrance(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """ADR 0020: only administrators sign in at /admin/login."""
    for role in (UserRole.FACILITY_CUSTODIAN, UserRole.DEAN_OF_RESEARCH):
        person = seed_user(role)
        response = client.post(
            "/api/v1/auth/login",
            json={
                "registration_number": person.registration_number,
                "password": "not-used-directly-seeded12",
                "portal": "admin",
            },
        )
        assert response.status_code in (401, 403), f"{role}: {response.status_code}"
