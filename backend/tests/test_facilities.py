"""Facility and equipment catalogue: scoping and CRUD (real PostgreSQL)."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
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


@pytest.fixture
def other_department(client: TestClient, world: World) -> str:
    school_id = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Science School"}
    ).json()["id"]
    department_id: str = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": school_id, "name": "Chemistry"},
    ).json()["id"]
    return department_id


def _facility(client: TestClient, user: SeededUser, **overrides: object) -> dict[str, object]:
    response = client.post(
        "/api/v1/facilities",
        headers=auth(user),
        json={"name": "Soil Lab", "location": "Block 32", **overrides},
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def test_coordinator_creates_facilities_only_in_their_department(
    client: TestClient, world: World, other_department: str
) -> None:
    created = _facility(client, world.coordinator)
    assert created["department_id"] == world.department_id
    # Asking for another department is refused rather than silently moved.
    assert (
        client.post(
            "/api/v1/facilities",
            headers=auth(world.coordinator),
            json={"name": "Elsewhere", "department_id": other_department},
        ).status_code
        == 403
    )
    # Admins can create anywhere.
    assert (
        client.post(
            "/api/v1/facilities",
            headers=auth(world.admin),
            json={"name": "Chem Lab", "department_id": other_department},
        ).status_code
        == 201
    )


def test_catalogue_is_readable_by_everyone_but_writable_by_managers(
    client: TestClient, world: World
) -> None:
    facility = _facility(client, world.coordinator)
    facility_id = facility["id"]

    for user in (world.student, world.faculty):
        assert client.get("/api/v1/facilities", headers=auth(user)).status_code == 200
        assert (
            client.get(f"/api/v1/facilities/{facility_id}", headers=auth(user)).status_code == 200
        )
        assert (
            client.post("/api/v1/facilities", headers=auth(user), json={"name": "Nope"}).status_code
            == 403
        )
        assert (
            client.patch(
                f"/api/v1/facilities/{facility_id}", headers=auth(user), json={"name": "Nope"}
            ).status_code
            == 403
        )


def test_out_of_scope_coordinator_cannot_manage(
    client: TestClient,
    world: World,
    other_department: str,
    seed_user: Callable[..., SeededUser],
) -> None:
    facility = _facility(client, world.coordinator)
    outsider = seed_user(
        UserRole.RESEARCH_COORDINATOR,
        department_id=other_department,
        coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
        coordinator_scope_id=other_department,
    )
    assert (
        client.patch(
            f"/api/v1/facilities/{facility['id']}",
            headers=auth(outsider),
            json={"location": "Moved"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/equipment",
            headers=auth(outsider),
            json={"facility_id": facility["id"], "name": "Sneaky microscope"},
        ).status_code
        == 403
    )
    assert (
        client.delete(f"/api/v1/facilities/{facility['id']}", headers=auth(outsider)).status_code
        == 403
    )


def test_duplicate_facility_name_in_a_department(client: TestClient, world: World) -> None:
    _facility(client, world.coordinator)
    assert (
        client.post(
            "/api/v1/facilities", headers=auth(world.coordinator), json={"name": "Soil Lab"}
        ).status_code
        == 409
    )


def test_equipment_crud_and_listing(client: TestClient, world: World) -> None:
    facility = _facility(client, world.coordinator)
    created = client.post(
        "/api/v1/equipment",
        headers=auth(world.coordinator),
        json={
            "facility_id": facility["id"],
            "name": "Soil moisture probe",
            "category": "sensors",
            "max_hours": 4,
            "min_lead_hours": 2,
            "students_allowed": True,
        },
    )
    assert created.status_code == 201, created.text
    equipment = created.json()
    assert equipment["facility_name"] == "Soil Lab"
    assert equipment["department_id"] == world.department_id

    listed = client.get(
        "/api/v1/equipment", headers=auth(world.student), params={"category": "sensors"}
    ).json()
    assert [item["name"] for item in listed["items"]] == ["Soil moisture probe"]

    updated = client.patch(
        f"/api/v1/equipment/{equipment['id']}",
        headers=auth(world.coordinator),
        json={"maintenance_status": "maintenance", "max_hours": 6},
    )
    assert updated.status_code == 200
    assert updated.json()["maintenance_status"] == "maintenance"
    assert updated.json()["max_hours"] == 6

    assert (
        client.delete(
            f"/api/v1/equipment/{equipment['id']}", headers=auth(world.coordinator)
        ).status_code
        == 204
    )
    assert (
        client.get(f"/api/v1/equipment/{equipment['id']}", headers=auth(world.student)).status_code
        == 404
    )


def test_a_facility_names_the_department_that_runs_it(client: TestClient, world: World) -> None:
    """The choice made on the form has to be visible afterwards.

    A facility with no department can be managed by administrators alone, so
    which one it is -- or that there is none -- is not a detail.
    """
    inside = client.post(
        "/api/v1/facilities",
        headers=auth(world.admin),
        json={"name": "Departmental Lab", "department_id": world.department_id},
    )
    assert inside.status_code in (200, 201), inside.text
    assert inside.json()["department_name"]

    university_wide = client.post(
        "/api/v1/facilities",
        headers=auth(world.admin),
        json={"name": "Central Instrumentation"},
    )
    assert university_wide.status_code in (200, 201), university_wide.text
    assert university_wide.json()["department_id"] is None
    assert university_wide.json()["department_name"] is None


def test_a_custodian_cannot_delete_the_facility_they_look_after(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """Looking after a room is not the power to abolish it.

    Deletion was gated object-level, the same gate as editing -- and a
    custodian passes that for their own facility, which is exactly the
    reasoning that already keeps custodian ASSIGNMENT at department level.
    It was the more dangerous of the two: `equipment` cascades from
    `facilities` and `bookings` cascades from `equipment`, so one press took
    the room, its equipment and every booking anyone held on it.
    """
    facility = _facility(client, world.coordinator, department_id=world.department_id)
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)
    assigned = client.put(
        f"/api/v1/facilities/{facility['id']}/custodian",
        headers=auth(world.coordinator),
        json={"user_id": str(custodian.id)},
    )
    assert assigned.status_code == 200, assigned.text

    refused = client.delete(f"/api/v1/facilities/{facility['id']}", headers=auth(custodian))

    assert refused.status_code == 403, refused.text
    # Still there, and still theirs to run.
    assert (
        client.get(f"/api/v1/facilities/{facility['id']}", headers=auth(custodian)).status_code
        == 200
    )


def test_a_custodian_still_manages_the_facility_they_hold(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """The narrowing is deletion only: the day-to-day powers stay."""
    facility = _facility(client, world.coordinator, department_id=world.department_id)
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)
    assigned = client.put(
        f"/api/v1/facilities/{facility['id']}/custodian",
        headers=auth(world.coordinator),
        json={"user_id": str(custodian.id)},
    )
    assert assigned.status_code == 200, assigned.text
    fetched = client.get(f"/api/v1/facilities/{facility['id']}", headers=auth(custodian)).json()
    assert fetched["custodian_id"] == str(custodian.id), fetched

    renamed = client.patch(
        f"/api/v1/facilities/{facility['id']}",
        headers=auth(custodian),
        json={"name": "Soil and Water Lab"},
    )

    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Soil and Water Lab"


def test_the_coordinator_may_still_delete_it(client: TestClient, world: World) -> None:
    """Creating a facility is a department decision; deleting one is the same
    decision in reverse, so it stays with the same people."""
    facility = _facility(client, world.coordinator, department_id=world.department_id)

    removed = client.delete(f"/api/v1/facilities/{facility['id']}", headers=auth(world.coordinator))

    assert removed.status_code == 204, removed.text
