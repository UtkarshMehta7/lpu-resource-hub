"""Who oversees my department, and where to read about them.

A faculty member's coordinator verifies their profile, reviews their projects
and approves their bookings. Until now the only way to find out who that was
was to ask somebody.
"""

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


def test_faculty_can_see_who_oversees_their_department(client: TestClient, world: World) -> None:
    response = client.get("/api/v1/me/department", headers=auth(world.faculty))

    assert response.status_code == 200
    body = response.json()
    assert body["department_name"]
    assert body["user_id"] == str(world.coordinator.id), "their actual coordinator"
    assert body["full_name"]
    assert body["registration_number"], "so the link can be labelled with the UID"


def test_a_student_sees_theirs_too(client: TestClient, world: World) -> None:
    body = client.get("/api/v1/me/department", headers=auth(world.student)).json()

    assert body["user_id"] == str(world.coordinator.id)


def test_a_department_with_nobody_overseeing_it_says_so(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """Silence would read as a bug. "There is no coordinator" explains why
    nothing is being verified."""
    school_id = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Science"}
    ).json()["id"]
    orphan = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": school_id, "name": "Physics"},
    ).json()["id"]
    member = seed_user(UserRole.FACULTY, department_id=orphan)

    body = client.get("/api/v1/me/department", headers=auth(member)).json()

    assert body["department_name"] == "Physics"
    assert body["user_id"] is None


def test_somebody_with_no_department_gets_nothing(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    stray = seed_user(UserRole.FACULTY)

    response = client.get("/api/v1/me/department", headers=auth(stray))

    assert response.status_code == 200
    assert response.json() is None


def test_signing_in_is_required(client: TestClient) -> None:
    assert client.get("/api/v1/me/department").status_code == 401
