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


def make_facility(
    client: TestClient, world: World, name: str, *, in_department: bool = False
) -> str:
    """A facility, optionally belonging to the world's department.

    Departmentless by default, which is what the object-level custodian tests
    want -- no department means no coordinator can reach it, so only the
    custodian column decides. Pass `in_department=True` for the tests about
    department-level scope, where it is the whole point.
    """
    payload: dict[str, object] = {"name": name}
    if in_department:
        payload["department_id"] = world.department_id
    created = client.post("/api/v1/facilities", headers=auth(world.admin), json=payload)
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
    # Two, and the second is tightly scoped: PROJECT_REVIEW lets a dean decide
    # work that CROSSES departments and nothing else (ADR 0032), enforced in
    # projects/policies.py rather than by the permission. Holding it says a
    # person may review *a* project, never every project.
    assert held == {Permission.ANALYTICS_READ, Permission.PROJECT_REVIEW}


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


# --- who may appoint a custodian (ADR 0030) --------------------------------


def custodian_body(number: str, department_id: str | None = None) -> dict[str, object]:
    body: dict[str, object] = {"registration_number": number, "full_name": "New Custodian"}
    if department_id is not None:
        body["department_id"] = department_id
    return body


def test_a_coordinator_appoints_a_custodian_for_their_own_department(
    client: TestClient, world: World
) -> None:
    """The gap this closes: a coordinator could assign a custodian to a
    facility but could not create one, so the picker's empty state was a dead
    end that ended in an administrator's inbox."""
    response = client.post(
        "/api/v1/facility-custodians",
        headers=auth(world.coordinator),
        json=custodian_body("12499001"),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["role"] == "facility_custodian"
    # Their own department, not one they named.
    assert body["user"]["department_id"] == world.department_id
    assert body["temporary_password"]


def test_the_request_cannot_name_a_role(client: TestClient, world: World) -> None:
    """The role is a constant of the route, not a field.

    CREATABLE_ROLE maps each role to exactly one successor, which is what lets
    an ordinary appointment derive the role from the caller. A `role` in the
    body would undo that, so one sent anyway must be ignored rather than
    honoured.
    """
    response = client.post(
        "/api/v1/facility-custodians",
        headers=auth(world.coordinator),
        json={**custodian_body("12499002"), "role": "admin"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["user"]["role"] == "facility_custodian"


def test_a_coordinator_cannot_appoint_into_another_department(
    client: TestClient, world: World
) -> None:
    other_school = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Elsewhere School"}
    ).json()["id"]
    other_department = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": other_school, "name": "Elsewhere"},
    ).json()["id"]

    response = client.post(
        "/api/v1/facility-custodians",
        headers=auth(world.coordinator),
        json=custodian_body("12499003", other_department),
    )

    assert response.status_code == 403, response.text


def test_an_administrator_may_appoint_a_custodian_anywhere(
    client: TestClient, world: World
) -> None:
    response = client.post(
        "/api/v1/facility-custodians",
        headers=auth(world.admin),
        json=custodian_body("12499004", world.department_id),
    )

    assert response.status_code == 201, response.text
    assert response.json()["user"]["role"] == "facility_custodian"


@pytest.mark.parametrize("role", [UserRole.FACULTY, UserRole.STUDENT])
def test_nobody_below_a_coordinator_may_appoint_one(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser], role: UserRole
) -> None:
    person = seed_user(role, department_id=world.department_id)

    response = client.post(
        "/api/v1/facility-custodians",
        headers=auth(person),
        json=custodian_body("12499005"),
    )

    assert response.status_code in (403, 422), response.text


def test_a_custodian_cannot_appoint_another_custodian(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """Somebody who looks after rooms must not be able to mint peers who look
    after others."""
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)

    response = client.post(
        "/api/v1/facility-custodians",
        headers=auth(custodian),
        json=custodian_body("12499006"),
    )

    assert response.status_code == 403, response.text


def test_a_coordinator_can_remove_a_custodian_they_appointed(
    client: TestClient, world: World
) -> None:
    """Creating without removing is the dead end in the other direction."""
    created = client.post(
        "/api/v1/facility-custodians",
        headers=auth(world.coordinator),
        json=custodian_body("12499007"),
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["user"]["id"]

    impact = client.get(f"/api/v1/users/{user_id}/deletion-impact", headers=auth(world.coordinator))
    removed = client.delete(f"/api/v1/users/{user_id}", headers=auth(world.coordinator))

    assert impact.status_code == 200, impact.text
    assert removed.status_code == 204, removed.text


# --- putting a facility in somebody's care ---------------------------------


def test_an_admin_assigns_a_custodian_and_the_facility_names_them(
    client: TestClient,
    world: World,
    seed_user: Callable[..., SeededUser],
) -> None:
    facility = make_facility(client, world, "Assignable Lab")
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)

    assigned = client.put(
        f"/api/v1/facilities/{facility}/custodian",
        headers=auth(world.admin),
        json={"user_id": str(custodian.id)},
    )

    assert assigned.status_code == 200, assigned.text
    body = assigned.json()
    assert body["custodian_id"] == str(custodian.id)
    # Named, not just referenced: an id alone tells a reader nothing about
    # whether the right person holds the room.
    assert body["custodian_name"]
    assert body["custodian_registration_number"]

    # And the assignment is what makes the role usable at all.
    edited = client.patch(
        f"/api/v1/facilities/{facility}",
        headers=auth(custodian),
        json={"location": "Block 7"},
    )
    assert edited.status_code == 200, edited.text


def test_a_custodian_cannot_hand_their_own_facility_to_somebody_else(
    client: TestClient,
    world: World,
    seed_user: Callable[..., SeededUser],
) -> None:
    """The reason this is its own endpoint rather than a FacilityUpdate field.

    A custodian passes the object-level check for their own facility, so an
    assignment folded into the ordinary edit would let them hand the room
    away -- or take a colleague's. Deciding who holds a facility is
    department-level, and a custodian holds no department.
    """
    facility = make_facility(client, world, "Contested Lab")
    mine = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)
    theirs = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)
    client.put(
        f"/api/v1/facilities/{facility}/custodian",
        headers=auth(world.admin),
        json={"user_id": str(mine.id)},
    )

    handover = client.put(
        f"/api/v1/facilities/{facility}/custodian",
        headers=auth(mine),
        json={"user_id": str(theirs.id)},
    )
    assert handover.status_code == 403, handover.text

    # Nor may they drop it, which would leave the room unattended.
    cleared = client.put(
        f"/api/v1/facilities/{facility}/custodian",
        headers=auth(mine),
        json={"user_id": None},
    )
    assert cleared.status_code == 403

    still = client.get(f"/api/v1/facilities/{facility}", headers=auth(world.admin)).json()
    assert still["custodian_id"] == str(mine.id)


def test_a_coordinator_assigns_inside_their_department_and_not_outside_it(
    client: TestClient,
    world: World,
    seed_user: Callable[..., SeededUser],
) -> None:
    ours = make_facility(client, world, "Our Lab", in_department=True)
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)

    inside = client.put(
        f"/api/v1/facilities/{ours}/custodian",
        headers=auth(world.coordinator),
        json={"user_id": str(custodian.id)},
    )
    assert inside.status_code == 200, inside.text

    # A facility in another department is out of their reach.
    other_school = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Science School"}
    ).json()["id"]
    other_department = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": other_school, "name": "Physics"},
    ).json()["id"]
    theirs = client.post(
        "/api/v1/facilities",
        headers=auth(world.admin),
        json={"name": "Their Lab", "department_id": other_department},
    ).json()["id"]

    outside = client.put(
        f"/api/v1/facilities/{theirs}/custodian",
        headers=auth(world.coordinator),
        json={"user_id": str(custodian.id)},
    )
    assert outside.status_code == 403


def test_only_a_custodian_may_be_made_one(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """A faculty member in the column would look looked-after and not be.

    They hold no FACILITY_MANAGE at all, so the facility would simply have
    nobody -- a silent nothing is worse than a refusal.
    """
    facility = make_facility(client, world, "Mislabelled Lab")

    response = client.put(
        f"/api/v1/facilities/{facility}/custodian",
        headers=auth(world.admin),
        json={"user_id": str(world.faculty.id)},
    )

    assert response.status_code == 422, response.text


def test_a_custodian_must_belong_to_the_department_that_runs_the_facility(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """Otherwise the department's coordinator oversees nobody again."""
    facility = make_facility(client, world, "Departmental Lab", in_department=True)
    other_school = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Arts School"}
    ).json()["id"]
    other_department = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": other_school, "name": "History"},
    ).json()["id"]
    stranger = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=other_department)

    response = client.put(
        f"/api/v1/facilities/{facility}/custodian",
        headers=auth(world.admin),
        json={"user_id": str(stranger.id)},
    )

    assert response.status_code == 422, response.text


def test_clearing_a_custodian_leaves_the_facility_between_custodians(
    client: TestClient,
    world: World,
    seed_user: Callable[..., SeededUser],
) -> None:
    facility = make_facility(client, world, "Vacated Lab")
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)
    client.put(
        f"/api/v1/facilities/{facility}/custodian",
        headers=auth(world.admin),
        json={"user_id": str(custodian.id)},
    )

    cleared = client.put(
        f"/api/v1/facilities/{facility}/custodian",
        headers=auth(world.admin),
        json={"user_id": None},
    )

    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["custodian_id"] is None
    # The facility survives; only the authority over it went away.
    assert cleared.json()["name"] == "Vacated Lab"
    # And the former custodian can no longer touch it.
    refused = client.patch(
        f"/api/v1/facilities/{facility}",
        headers=auth(custodian),
        json={"location": "Nowhere"},
    )
    assert refused.status_code == 403


def test_assigning_a_custodian_is_audited(
    client: TestClient,
    world: World,
    seed_user: Callable[..., SeededUser],
) -> None:
    """A change of authority, not of a label, so it leaves a record."""
    facility = make_facility(client, world, "Audited Lab")
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)
    client.put(
        f"/api/v1/facilities/{facility}/custodian",
        headers=auth(world.admin),
        json={"user_id": str(custodian.id)},
    )
    client.put(
        f"/api/v1/facilities/{facility}/custodian",
        headers=auth(world.admin),
        json={"user_id": None},
    )

    logs = client.get(
        "/api/v1/admin/audit-logs", headers=auth(world.admin), params={"entity_type": "facility"}
    )
    assert logs.status_code == 200, logs.text
    actions = [row["action"] for row in logs.json()["items"]]
    assert "facility.custodian_assigned" in actions
    assert "facility.custodian_cleared" in actions


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


# --- a dean who can actually do the job ------------------------------------


def test_a_dean_compares_departments(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """The question a Dean of Research actually asks.

    Before this the only answer available was one institution-wide total,
    which hides precisely what it is wanted for: which departments are
    producing and which are slipping.
    """
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)

    response = client.get("/api/v1/analytics/by-department", headers=auth(dean))

    assert response.status_code == 200, response.text
    rows = response.json()
    assert rows, "a department exists, so the comparison cannot be empty"
    row = rows[0]
    for field in (
        "department_name",
        "researchers",
        "students",
        "projects_active",
        "publications",
        "milestones_overdue",
        "milestones_at_risk",
        "verification_pending",
    ):
        assert field in row, field


def test_a_dean_narrows_the_overview_to_one_department(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)

    whole = client.get("/api/v1/analytics/overview", headers=auth(dean))
    narrowed = client.get(
        "/api/v1/analytics/overview",
        headers=auth(dean),
        params={"department_id": world.department_id},
    )

    assert whole.status_code == 200 and narrowed.status_code == 200, narrowed.text
    assert whole.json()["scope"] == "platform"
    assert narrowed.json()["scope"] == "department"
    assert narrowed.json()["department_id"] == world.department_id


def test_a_coordinator_cannot_read_another_department(client: TestClient, world: World) -> None:
    """Narrowing is for institution-wide readers. A coordinator asking for
    somebody else's department is refused rather than quietly handed their
    own -- silently substituting the answer is how somebody comes to believe
    a figure that is not the one they asked for."""
    other_school = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Other School"}
    ).json()["id"]
    other_department = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": other_school, "name": "Other Department"},
    ).json()["id"]

    response = client.get(
        "/api/v1/analytics/overview",
        headers=auth(world.coordinator),
        params={"department_id": other_department},
    )

    assert response.status_code == 403, response.text


def test_a_coordinator_cannot_compare_departments(client: TestClient, world: World) -> None:
    response = client.get("/api/v1/analytics/by-department", headers=auth(world.coordinator))

    assert response.status_code == 403, response.text


def test_the_directory_names_a_person_s_department(client: TestClient, world: World) -> None:
    """A card carrying only a UUID tells a reader none of what they came for,
    and which department somebody belongs to is the first thing anyone asks
    about a person."""
    response = client.get("/api/v1/researchers", headers=auth(world.faculty))

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items
    named = [card for card in items if card.get("department_id")]
    assert named, "the fixture should have somebody in a department"
    assert all(card["department_name"] for card in named)


# --- a dean decides what crosses departments (ADR 0032) --------------------


def _pending_cross_department_project(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> str:
    """A project whose team reaches outside its own department.

    Nobody at department level can review this properly: a coordinator sees
    one department, and half this team is in another.
    """
    other_school = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Second School"}
    ).json()["id"]
    other_department = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": other_school, "name": "Second Department"},
    ).json()["id"]
    outsider = seed_user(UserRole.STUDENT, department_id=other_department)

    created = client.post(
        "/api/v1/projects",
        headers=auth(world.faculty),
        json={"title": "Across two departments", "summary": "Joint work.", "description": "x"},
    )
    assert created.status_code == 201, created.text
    project_id: str = created.json()["id"]
    added = client.post(
        f"/api/v1/projects/{project_id}/members",
        headers=auth(world.faculty),
        json={"user_id": str(outsider.id), "member_role": "Research assistant"},
    )
    assert added.status_code in (200, 201), added.text
    submitted = client.post(f"/api/v1/projects/{project_id}/submit", headers=auth(world.faculty))
    assert submitted.status_code == 200, submitted.text
    return project_id


def test_a_dean_reviews_work_that_crosses_departments(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)
    project_id = _pending_cross_department_project(client, world, seed_user)

    queue = client.get("/api/v1/coordinator/review-queue", headers=auth(dean))
    assert queue.status_code == 200, queue.text
    assert any(card["id"] == project_id for card in queue.json())

    decided = client.post(
        f"/api/v1/projects/{project_id}/review",
        headers=auth(dean),
        json={"decision": "approve", "comment": "Worth doing across both."},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "active"


def test_a_dean_does_not_decide_ordinary_departmental_work(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """Otherwise the dean quietly replaces the coordinator who is meant to."""
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)
    created = client.post(
        "/api/v1/projects",
        headers=auth(world.faculty),
        json={"title": "One department only", "summary": "Local work.", "description": "x"},
    )
    project_id = created.json()["id"]
    client.post(f"/api/v1/projects/{project_id}/submit", headers=auth(world.faculty))

    queue = client.get("/api/v1/coordinator/review-queue", headers=auth(dean))
    decided = client.post(
        f"/api/v1/projects/{project_id}/review",
        headers=auth(dean),
        json={"decision": "approve"},
    )

    assert queue.status_code == 200
    assert all(card["id"] != project_id for card in queue.json())
    assert decided.status_code == 403, decided.text


def test_the_queue_and_the_decision_agree_for_a_dean(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """A queue offering what the review call refuses is a dead button."""
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)
    _pending_cross_department_project(client, world, seed_user)
    client.post(
        "/api/v1/projects",
        headers=auth(world.faculty),
        json={"title": "Purely local", "summary": "s", "description": "d"},
    )

    offered = client.get("/api/v1/coordinator/review-queue", headers=auth(dean)).json()

    for card in offered:
        decided = client.post(
            f"/api/v1/projects/{card['id']}/review",
            headers=auth(dean),
            json={"decision": "approve"},
        )
        assert decided.status_code == 200, decided.text


def test_a_coordinator_still_decides_their_own_department(client: TestClient, world: World) -> None:
    created = client.post(
        "/api/v1/projects",
        headers=auth(world.faculty),
        json={"title": "Coordinator decides", "summary": "s", "description": "d"},
    )
    project_id = created.json()["id"]
    client.post(f"/api/v1/projects/{project_id}/submit", headers=auth(world.faculty))

    decided = client.post(
        f"/api/v1/projects/{project_id}/review",
        headers=auth(world.coordinator),
        json={"decision": "approve"},
    )

    assert decided.status_code == 200, decided.text
