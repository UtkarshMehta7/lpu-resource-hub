"""Issuing a replacement temporary password when the first one was lost."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
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


def _create_student(client: TestClient, world: World) -> dict[str, object]:
    response = client.post(
        "/api/v1/users",
        headers=auth(world.faculty),
        json={"registration_number": "31313131", "full_name": "Forgetful Student"},
    )
    assert response.status_code == 201, response.json()
    body: dict[str, object] = response.json()
    return body


def test_a_reset_password_signs_the_user_in_and_the_old_one_stops_working(
    client: TestClient, world: World
) -> None:
    created = _create_student(client, world)
    original = created["temporary_password"]
    user = created["user"]
    assert isinstance(user, dict)

    response = client.post(
        f"/api/v1/admin/users/{user['id']}/temporary-password", headers=auth(world.admin)
    )

    assert response.status_code == 200
    replacement = response.json()["temporary_password"]
    assert replacement != original
    assert len(replacement) >= 12
    assert response.json()["user"]["must_change_password"] is True

    assert (
        client.post(
            "/api/v1/auth/login",
            json={"registration_number": "31313131", "password": original},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"registration_number": "31313131", "password": replacement},
        ).status_code
        == 200
    )


def test_a_reset_walls_the_account_off_again(client: TestClient, world: World) -> None:
    created = _create_student(client, world)
    user = created["user"]
    assert isinstance(user, dict)
    # The student has settled in with a password of their own.
    first_token = client.post(
        "/api/v1/auth/login",
        json={"registration_number": "31313131", "password": created["temporary_password"]},
    ).json()["access_token"]
    client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {first_token}"},
        json={
            "current_password": created["temporary_password"],
            "new_password": "a-settled-password-1",
        },
    )

    replacement = client.post(
        f"/api/v1/admin/users/{user['id']}/temporary-password", headers=auth(world.admin)
    ).json()["temporary_password"]

    token = client.post(
        "/api/v1/auth/login",
        json={"registration_number": "31313131", "password": replacement},
    ).json()["access_token"]
    blocked = client.get("/api/v1/opportunities", headers={"Authorization": f"Bearer {token}"})
    assert blocked.status_code == 403
    assert blocked.json()["error"]["message"] == "password_change_required"


def test_a_reset_revokes_existing_sessions(client: TestClient, world: World) -> None:
    created = _create_student(client, world)
    user = created["user"]
    assert isinstance(user, dict)
    client.post(
        "/api/v1/auth/login",
        json={"registration_number": "31313131", "password": created["temporary_password"]},
    )
    refresh_cookie = client.cookies.get("refresh_token")
    assert refresh_cookie is not None

    client.post(f"/api/v1/admin/users/{user['id']}/temporary-password", headers=auth(world.admin))

    client.cookies.set("refresh_token", refresh_cookie)
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_a_reset_is_audited(client: TestClient, world: World) -> None:
    created = _create_student(client, world)
    user = created["user"]
    assert isinstance(user, dict)

    client.post(f"/api/v1/admin/users/{user['id']}/temporary-password", headers=auth(world.admin))

    logs = client.get(
        "/api/v1/admin/audit-logs",
        headers=auth(world.admin),
        params={"action": "user.password_reset", "entity_id": user["id"]},
    ).json()["items"]
    assert len(logs) == 1
    assert logs[0]["actor_id"] == str(world.admin.id)
    # The password itself is never written anywhere readable.
    assert str(created["temporary_password"]) not in str(logs[0])


def test_an_admin_cannot_reset_their_own_password_this_way(
    client: TestClient, world: World
) -> None:
    response = client.post(
        f"/api/v1/admin/users/{world.admin.id}/temporary-password", headers=auth(world.admin)
    )

    assert response.status_code == 409


def test_only_an_admin_may_reset_a_password(client: TestClient, world: World) -> None:
    for actor in (world.faculty, world.coordinator, world.student):
        response = client.post(
            f"/api/v1/admin/users/{world.other_student.id}/temporary-password",
            headers=auth(actor),
        )
        assert response.status_code == 403


def test_resetting_an_unknown_user_is_404(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/admin/users/11111111-1111-1111-1111-111111111111/temporary-password",
        headers=auth(world.admin),
    )

    assert response.status_code == 404


def test_a_reset_needs_authentication(client: TestClient, world: World) -> None:
    response = client.post(f"/api/v1/admin/users/{world.student.id}/temporary-password")

    assert response.status_code == 401


def test_seeded_roles_are_unaffected(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """A reset works on any role, not only accounts created through the API."""
    target = seed_user(UserRole.FACULTY)

    response = client.post(
        f"/api/v1/admin/users/{target.id}/temporary-password", headers=auth(world.admin)
    )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(target.id)
