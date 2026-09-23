"""Account provisioning down the institutional hierarchy.

Nobody signs themselves up. An admin appoints coordinators, a coordinator
appoints the faculty of the department they oversee, a faculty member enrols
their students, and a student appoints nobody. The role of a new account is
derived from its creator, so there is no role in the request to forge.
"""

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


def _create(
    client: TestClient, creator: SeededUser, **overrides: object
) -> tuple[int, dict[str, object]]:
    body = {
        "registration_number": "12345678",
        "full_name": "Someone New",
        **overrides,
    }
    response = client.post("/api/v1/users", headers=auth(creator), json=body)
    return response.status_code, response.json()


# ------------------------------------------------- the hierarchy, rung by rung


def test_an_admin_appoints_a_coordinator(client: TestClient, world: World) -> None:
    code, body = _create(client, world.admin, department_id=world.department_id)

    assert code == 201, body
    user = body["user"]
    assert isinstance(user, dict)
    assert user["role"] == "research_coordinator"
    assert user["must_change_password"] is True
    assert user["department_id"] == world.department_id
    # Appointed to oversee the department they were placed in, so they can
    # start work without a second admin step.
    assert user["coordinator_scope_type"] == CoordinatorScopeType.DEPARTMENT.value
    assert user["coordinator_scope_id"] == world.department_id
    assert isinstance(body["temporary_password"], str)
    assert len(str(body["temporary_password"])) >= 12


def test_a_coordinator_appoints_a_faculty_member(client: TestClient, world: World) -> None:
    code, body = _create(client, world.coordinator)

    assert code == 201, body
    user = body["user"]
    assert isinstance(user, dict)
    assert user["role"] == "faculty"
    # Into the department they oversee, which they did not have to name.
    assert user["department_id"] == world.department_id


def test_a_faculty_member_enrols_a_student(client: TestClient, world: World) -> None:
    code, body = _create(client, world.faculty)

    assert code == 201, body
    user = body["user"]
    assert isinstance(user, dict)
    assert user["role"] == "student"
    assert user["department_id"] == world.department_id

    # ...and the new account can actually sign in with what it was given.
    login = client.post(
        "/api/v1/auth/login",
        json={"registration_number": "12345678", "password": body["temporary_password"]},
    )
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True


def test_a_student_appoints_nobody(client: TestClient, world: World) -> None:
    code, _ = _create(client, world.student)

    assert code == 403


def test_provisioning_needs_authentication(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/users",
        json={"registration_number": "12345678", "full_name": "Nobody"},
    )

    assert response.status_code == 401


# --------------------------------------------- no role may be asked for at all


@pytest.mark.parametrize("smuggled", ["admin", "research_coordinator", "faculty", "student"])
def test_a_role_in_the_payload_is_ignored_entirely(
    client: TestClient, world: World, smuggled: str
) -> None:
    """The classic escalation attempt. `role` is not a field on the request
    schema, so it cannot influence anything, whoever sends it."""
    code, body = _create(client, world.faculty, role=smuggled)

    assert code == 201, body
    user = body["user"]
    assert isinstance(user, dict)
    # A faculty member creates a student. Always.
    assert user["role"] == "student"


def test_a_coordinator_cannot_smuggle_their_way_to_an_admin(
    client: TestClient, world: World
) -> None:
    code, body = _create(client, world.coordinator, role="admin")

    assert code == 201, body
    user = body["user"]
    assert isinstance(user, dict)
    assert user["role"] == "faculty"


def test_nobody_can_promote_themselves(client: TestClient, world: World) -> None:
    """Role changes are an admin action on someone else, never a self-service."""
    for actor in (world.student, world.faculty, world.coordinator):
        response = client.post(
            f"/api/v1/admin/users/{actor.id}/role",
            headers=auth(actor),
            json={"role": "admin"},
        )
        assert response.status_code == 403, actor.id

    # Even an admin may not change their own role.
    own = client.post(
        f"/api/v1/admin/users/{world.admin.id}/role",
        headers=auth(world.admin),
        json={"role": "student"},
    )
    assert own.status_code == 409


def test_a_profile_update_cannot_change_a_role(client: TestClient, world: World) -> None:
    response = client.patch(
        f"/api/v1/admin/users/{world.student.id}",
        headers=auth(world.admin),
        json={"full_name": "Renamed", "role": "admin", "is_active": False},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "student"
    assert response.json()["is_active"] is True


# --------------------------------------------------------------------- scope


def test_a_coordinator_cannot_reach_outside_their_scope(client: TestClient, world: World) -> None:
    school_id = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Science School"}
    ).json()["id"]
    other_department = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": school_id, "name": "Chemistry"},
    ).json()["id"]

    code, _ = _create(client, world.coordinator, department_id=other_department)

    assert code == 403


def test_a_faculty_member_cannot_reach_outside_their_department(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    school_id = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Arts School"}
    ).json()["id"]
    other_department = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": school_id, "name": "History"},
    ).json()["id"]

    code, _ = _create(client, world.faculty, department_id=other_department)

    assert code == 403


def test_an_admin_must_name_a_department_for_a_coordinator(
    client: TestClient, world: World
) -> None:
    """A coordinator with no scope oversees nothing, so this is refused rather
    than creating a useless account."""
    code, _ = _create(client, world.admin)

    assert code == 422


def test_an_unknown_department_is_refused(client: TestClient, world: World) -> None:
    code, _ = _create(client, world.admin, department_id="11111111-1111-1111-1111-111111111111")

    assert code == 404


def test_an_unverified_faculty_member_cannot_enrol_anyone(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    newcomer = seed_user(UserRole.FACULTY, department_id=world.department_id)

    code, body = _create(client, newcomer)

    assert code == 403
    assert "verify" in body["error"]["message"]


# ------------------------------------------------------- the account that lands


def test_a_new_account_is_walled_off_until_the_password_is_changed(
    client: TestClient, world: World
) -> None:
    _, created = _create(client, world.faculty)
    temporary_password = created["temporary_password"]
    token = client.post(
        "/api/v1/auth/login",
        json={"registration_number": "12345678", "password": temporary_password},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Their own account is readable, so the UI can greet them...
    assert client.get("/api/v1/me", headers=headers).status_code == 200
    # ...but everything else is closed, with a code the frontend can act on.
    blocked = client.get("/api/v1/opportunities", headers=headers)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["message"] == "password_change_required"

    changed = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": temporary_password, "new_password": "my-own-password-123"},
    )
    assert changed.status_code == 204

    fresh = client.post(
        "/api/v1/auth/login",
        json={"registration_number": "12345678", "password": "my-own-password-123"},
    )
    assert fresh.status_code == 200
    assert fresh.json()["user"]["must_change_password"] is False


def test_a_duplicate_registration_number_is_refused(client: TestClient, world: World) -> None:
    assert _create(client, world.faculty)[0] == 201
    # Same number, different case.
    assert _create(client, world.faculty, registration_number="12345678")[0] == 409


def test_provisioning_is_audited_and_records_the_creator(client: TestClient, world: World) -> None:
    _, created = _create(client, world.faculty)
    user = created["user"]
    assert isinstance(user, dict)

    logs = client.get(
        "/api/v1/admin/audit-logs",
        headers=auth(world.admin),
        params={"action": "user.created", "entity_id": user["id"]},
    ).json()["items"]
    assert len(logs) == 1
    assert logs[0]["actor_id"] == str(world.faculty.id)

    # ...and the account itself remembers who let them in.
    listed = client.get(
        "/api/v1/admin/users", headers=auth(world.admin), params={"page_size": 100}
    ).json()["items"]
    created_row = next(row for row in listed if row["id"] == user["id"])
    assert created_row["created_by"] == str(world.faculty.id)
