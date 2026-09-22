"""Audit log read endpoint integration tests against a real PostgreSQL database."""

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


def test_audit_logs_requires_admin(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    faculty = seed_user(UserRole.FACULTY)

    response = client.get("/api/v1/admin/audit-logs", headers=_auth_headers(faculty))

    assert response.status_code == 403


def test_audit_logs_anonymous_is_401(client: TestClient) -> None:
    response = client.get("/api/v1/admin/audit-logs")

    assert response.status_code == 401


def test_audit_logs_records_role_and_activation_changes(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    student = seed_user(UserRole.STUDENT)

    client.post(
        f"/api/v1/admin/users/{student.id}/role",
        headers=_auth_headers(admin),
        json={"role": "faculty"},
    )
    client.post(f"/api/v1/admin/users/{student.id}/deactivate", headers=_auth_headers(admin))

    response = client.get(
        "/api/v1/admin/audit-logs",
        params={"entity_id": str(student.id)},
        headers=_auth_headers(admin),
    )

    assert response.status_code == 200
    actions = {log["action"] for log in response.json()["items"]}
    assert actions == {"user.role_changed", "user.deactivated"}


def test_audit_logs_filter_by_action(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    student_a = seed_user(UserRole.STUDENT)
    student_b = seed_user(UserRole.STUDENT)

    client.post(f"/api/v1/admin/users/{student_a.id}/deactivate", headers=_auth_headers(admin))
    client.post(
        f"/api/v1/admin/users/{student_b.id}/role",
        headers=_auth_headers(admin),
        json={"role": "faculty"},
    )

    response = client.get(
        "/api/v1/admin/audit-logs",
        params={"action": "user.deactivated"},
        headers=_auth_headers(admin),
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["entity_id"] == str(student_a.id)


def test_audit_logs_pagination(client: TestClient, seed_user: Callable[..., SeededUser]) -> None:
    admin = seed_user(UserRole.ADMIN)
    students = [seed_user(UserRole.STUDENT) for _ in range(3)]
    for student in students:
        client.post(f"/api/v1/admin/users/{student.id}/deactivate", headers=_auth_headers(admin))

    response = client.get(
        "/api/v1/admin/audit-logs", params={"page_size": 2}, headers=_auth_headers(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["total"] == 3
