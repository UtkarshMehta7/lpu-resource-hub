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
