"""Admin user-management integration tests against a real PostgreSQL database."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.users.models import UserRole
from tests.conftest import SeededUser

pytestmark = pytest.mark.db


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


def _auth_headers(user: SeededUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.access_token}"}


def _create_department(client: TestClient, admin: SeededUser) -> str:
    school_response = client.post(
        "/api/v1/admin/schools", headers=_auth_headers(admin), json={"name": "Demo School"}
    )
    school_id = school_response.json()["id"]
    department_response = client.post(
        "/api/v1/admin/departments",
        headers=_auth_headers(admin),
        json={"school_id": school_id, "name": "Demo Department"},
    )
    department_id: str = department_response.json()["id"]
    return department_id


def test_list_users_requires_admin(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    seed_user(UserRole.STUDENT)
    faculty = seed_user(UserRole.FACULTY)

    response = client.get("/api/v1/admin/users", headers=_auth_headers(faculty))

    assert response.status_code == 403


def test_list_users_paginates_and_filters(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    seed_user(UserRole.STUDENT)
    seed_user(UserRole.STUDENT)
    seed_user(UserRole.FACULTY)

    response = client.get(
        "/api/v1/admin/users", params={"role": "student"}, headers=_auth_headers(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert all(item["role"] == "student" for item in body["items"])


def test_list_users_page_size_is_respected(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    for _ in range(3):
        seed_user(UserRole.STUDENT)

    response = client.get(
        "/api/v1/admin/users", params={"page_size": 2}, headers=_auth_headers(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["total"] == 4  # 3 students + the admin itself


def test_patch_user_updates_only_profile_fields_not_role_or_active(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    student = seed_user(UserRole.STUDENT)

    response = client.patch(
        f"/api/v1/admin/users/{student.id}",
        headers=_auth_headers(admin),
        json={
            "full_name": "Updated Name",
            "role": "admin",  # not a field on AdminUserUpdate: ignored
            "is_active": False,  # not a field on AdminUserUpdate: ignored
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Updated Name"
    assert body["role"] == "student"
    assert body["is_active"] is True


def test_patch_user_sets_coordinator_scope(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)
    department_id = _create_department(client, admin)

    response = client.patch(
        f"/api/v1/admin/users/{coordinator.id}",
        headers=_auth_headers(admin),
        json={"coordinator_scope_type": "department", "coordinator_scope_id": department_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["coordinator_scope_type"] == "department"
    assert body["coordinator_scope_id"] == department_id


def test_patch_user_rejects_a_department_scope_id_that_does_not_exist(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)
    fake_department_id = "11111111-1111-1111-1111-111111111111"

    response = client.patch(
        f"/api/v1/admin/users/{coordinator.id}",
        headers=_auth_headers(admin),
        json={"coordinator_scope_type": "department", "coordinator_scope_id": fake_department_id},
    )

    assert response.status_code == 422


def test_patch_unknown_user_is_404(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)

    response = client.patch(
        "/api/v1/admin/users/11111111-1111-1111-1111-111111111111",
        headers=_auth_headers(admin),
        json={"full_name": "Ghost"},
    )

    assert response.status_code == 404


def test_change_role_happy_path_writes_audit_row(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    student = seed_user(UserRole.STUDENT)

    response = client.post(
        f"/api/v1/admin/users/{student.id}/role",
        headers=_auth_headers(admin),
        json={"role": "faculty"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "faculty"

    audit_response = client.get(
        "/api/v1/admin/audit-logs",
        params={"entity_id": str(student.id), "action": "user.role_changed"},
        headers=_auth_headers(admin),
    )
    assert audit_response.status_code == 200
    logs = audit_response.json()["items"]
    assert len(logs) == 1
    assert logs[0]["before"] == {"role": "student"}
    assert logs[0]["after"] == {"role": "faculty"}
    assert logs[0]["actor_id"] == str(admin.id)


def test_change_role_rejects_self_role_change(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)

    response = client.post(
        f"/api/v1/admin/users/{admin.id}/role",
        headers=_auth_headers(admin),
        json={"role": "faculty"},
    )

    assert response.status_code == 409


def test_change_role_of_a_different_admin_is_allowed_when_another_admin_remains(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    """With two admins, demoting one still leaves the actor as an active admin."""
    admin = seed_user(UserRole.ADMIN)
    other_admin = seed_user(UserRole.ADMIN)

    response = client.post(
        f"/api/v1/admin/users/{other_admin.id}/role",
        headers=_auth_headers(admin),
        json={"role": "faculty"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "faculty"


def test_activate_and_deactivate_happy_path(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    student = seed_user(UserRole.STUDENT)

    deactivate_response = client.post(
        f"/api/v1/admin/users/{student.id}/deactivate", headers=_auth_headers(admin)
    )
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False

    activate_response = client.post(
        f"/api/v1/admin/users/{student.id}/activate", headers=_auth_headers(admin)
    )
    assert activate_response.status_code == 200
    assert activate_response.json()["is_active"] is True


def test_deactivate_revokes_the_users_refresh_tokens(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    target = seed_user(UserRole.FACULTY, registration_number="TARGET0001")

    # A real session for the target, so there is something to revoke.
    login = client.post(
        "/api/v1/auth/login",
        json={"registration_number": "TARGET0001", "password": "not-used-directly-seeded12"},
    )
    assert login.status_code == 200
    target_id = str(target.id)
    refresh_cookie = client.cookies.get("refresh_token")
    assert refresh_cookie is not None

    deactivate_response = client.post(
        f"/api/v1/admin/users/{target_id}/deactivate", headers=_auth_headers(admin)
    )
    assert deactivate_response.status_code == 200

    client.cookies.set("refresh_token", refresh_cookie)
    refresh_response = client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 401


def test_deactivate_rejects_removing_the_last_active_admin(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)

    response = client.post(
        f"/api/v1/admin/users/{admin.id}/deactivate", headers=_auth_headers(admin)
    )

    assert response.status_code == 409


def test_deactivate_a_second_admin_is_allowed(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    other_admin = seed_user(UserRole.ADMIN)

    response = client.post(
        f"/api/v1/admin/users/{other_admin.id}/deactivate", headers=_auth_headers(admin)
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False
