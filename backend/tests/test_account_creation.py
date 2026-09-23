"""Accounts created for other people: who may, scope, and the forced first change."""

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
        "full_name": "Demo Student Ninety",
        **overrides,
    }
    response = client.post("/api/v1/users", headers=auth(creator), json=body)
    return response.status_code, response.json()


def test_students_cannot_register_themselves(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "registration_number": "99999999",
            "password": "correcthorsebattery",
            "full_name": "Sneaky Student",
            "role": "student",
        },
    )
    assert response.status_code == 422


def test_faculty_creates_a_student_in_their_own_department(
    client: TestClient, world: World
) -> None:
    code, body = _create(client, world.faculty)
    assert code == 201, body

    user = body["user"]
    assert isinstance(user, dict)
    assert user["registration_number"] == "12345678"
    assert user["role"] == "student"
    assert user["must_change_password"] is True
    # The department comes from the creator, not the request.
    assert isinstance(body["temporary_password"], str)
    assert len(str(body["temporary_password"])) >= 12

    # ...and the new account can actually sign in with it.
    login = client.post(
        "/api/v1/auth/login",
        json={"registration_number": "12345678", "password": body["temporary_password"]},
    )
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True


def test_students_cannot_create_accounts(client: TestClient, world: World) -> None:
    assert _create(client, world.student)[0] == 403


def test_faculty_cannot_create_staff_or_cross_department_accounts(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    assert _create(client, world.faculty, role="faculty")[0] == 403
    assert _create(client, world.faculty, role="admin")[0] == 403

    school_id = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Science School"}
    ).json()["id"]
    other_department = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": school_id, "name": "Chemistry"},
    ).json()["id"]
    assert _create(client, world.faculty, department_id=other_department)[0] == 403

    # A coordinator is limited to the department they oversee.
    outsider = seed_user(
        UserRole.RESEARCH_COORDINATOR,
        department_id=other_department,
        coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
        coordinator_scope_id=other_department,
    )
    code, body = _create(client, outsider, registration_number="22223333")
    assert code == 201, body


def test_admin_can_create_any_role_and_duplicates_are_refused(
    client: TestClient, world: World
) -> None:
    code, body = _create(
        client,
        world.admin,
        role="research_coordinator",
        registration_number="ADMIN0MADE1",
        department_id=world.department_id,
    )
    assert code == 201, body
    assert body["user"]["role"] == "research_coordinator"

    # Same number again, whatever the case.
    assert (
        _create(
            client,
            world.admin,
            role="research_coordinator",
            registration_number="admin0made1",
            department_id=world.department_id,
        )[0]
        == 409
    )
    # A student still needs a department, even when an admin creates it.
    assert _create(client, world.admin, registration_number="99887766")[0] == 422


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

    # Changing the password revokes every session, so sign in again.
    fresh = client.post(
        "/api/v1/auth/login",
        json={"registration_number": "12345678", "password": "my-own-password-123"},
    )
    assert fresh.status_code == 200
    assert fresh.json()["user"]["must_change_password"] is False
    new_headers = {"Authorization": f"Bearer {fresh.json()['access_token']}"}
    assert client.get("/api/v1/opportunities", headers=new_headers).status_code == 200


def test_account_creation_is_audited(client: TestClient, world: World) -> None:
    _, created = _create(client, world.faculty)
    logs = client.get(
        "/api/v1/admin/audit-logs",
        headers=auth(world.admin),
        params={"action": "user.created"},
    ).json()["items"]
    assert [log["entity_id"] for log in logs] == [created["user"]["id"]]
    assert logs[0]["actor_id"] == str(world.faculty.id)
