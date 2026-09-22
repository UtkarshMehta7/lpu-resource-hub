"""Schools/departments admin CRUD integration tests against a real PostgreSQL database."""

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


def test_schools_and_departments_require_admin(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    faculty = seed_user(UserRole.FACULTY)

    assert client.get("/api/v1/admin/schools", headers=_auth_headers(faculty)).status_code == 403
    assert (
        client.post(
            "/api/v1/admin/schools", headers=_auth_headers(faculty), json={"name": "X"}
        ).status_code
        == 403
    )


def test_create_and_list_schools(client: TestClient, seed_user: Callable[..., SeededUser]) -> None:
    admin = seed_user(UserRole.ADMIN)

    create_response = client.post(
        "/api/v1/admin/schools", headers=_auth_headers(admin), json={"name": "School of Science"}
    )
    assert create_response.status_code == 201

    list_response = client.get("/api/v1/admin/schools", headers=_auth_headers(admin))
    assert list_response.status_code == 200
    names = [s["name"] for s in list_response.json()]
    assert "School of Science" in names


def test_create_school_rejects_duplicate_name(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    client.post("/api/v1/admin/schools", headers=_auth_headers(admin), json={"name": "Dup"})

    response = client.post(
        "/api/v1/admin/schools", headers=_auth_headers(admin), json={"name": "Dup"}
    )

    assert response.status_code == 409


def test_update_and_delete_school(client: TestClient, seed_user: Callable[..., SeededUser]) -> None:
    admin = seed_user(UserRole.ADMIN)
    school_id = client.post(
        "/api/v1/admin/schools", headers=_auth_headers(admin), json={"name": "Old Name"}
    ).json()["id"]

    patch_response = client.patch(
        f"/api/v1/admin/schools/{school_id}",
        headers=_auth_headers(admin),
        json={"name": "New Name"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "New Name"

    delete_response = client.delete(
        f"/api/v1/admin/schools/{school_id}", headers=_auth_headers(admin)
    )
    assert delete_response.status_code == 204

    remaining = client.get("/api/v1/admin/schools", headers=_auth_headers(admin)).json()
    assert school_id not in [s["id"] for s in remaining]


def test_create_department_requires_a_real_school(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)

    response = client.post(
        "/api/v1/admin/departments",
        headers=_auth_headers(admin),
        json={"school_id": "11111111-1111-1111-1111-111111111111", "name": "Physics"},
    )

    assert response.status_code == 404


def test_create_department_rejects_duplicate_name_within_school(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    school_id = client.post(
        "/api/v1/admin/schools", headers=_auth_headers(admin), json={"name": "Engineering"}
    ).json()["id"]
    client.post(
        "/api/v1/admin/departments",
        headers=_auth_headers(admin),
        json={"school_id": school_id, "name": "CS"},
    )

    response = client.post(
        "/api/v1/admin/departments",
        headers=_auth_headers(admin),
        json={"school_id": school_id, "name": "CS"},
    )

    assert response.status_code == 409


def test_deleting_a_department_clears_users_department_id(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    school_id = client.post(
        "/api/v1/admin/schools", headers=_auth_headers(admin), json={"name": "School A"}
    ).json()["id"]
    department_id = client.post(
        "/api/v1/admin/departments",
        headers=_auth_headers(admin),
        json={"school_id": school_id, "name": "Dept A"},
    ).json()["id"]

    delete_response = client.delete(
        f"/api/v1/admin/departments/{department_id}", headers=_auth_headers(admin)
    )
    assert delete_response.status_code == 204

    list_response = client.get("/api/v1/admin/departments", headers=_auth_headers(admin))
    assert department_id not in [d["id"] for d in list_response.json()]
