"""Two entrances, and a coordinator's authority following their department.

The sign-in pages are separate on purpose: administration is not somewhere an
ordinary user should land by accident, and an administrator arriving at the
main page would get a dashboard instead of the console they came for. A URL
alone enforces nothing, so the rule lives on the server.

Separately: a coordinator's scope *is* their department. Setting the role or
the department from the users page used to leave the scope untouched, which
produced a coordinator who oversaw nothing -- an empty verification queue and
403 on every decision, with nothing on screen saying why.
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

SEEDED_PASSWORD = "not-used-directly-seeded12"


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    return build_world(client, seed_user)


def _login(client: TestClient, user: SeededUser, portal: str | None) -> int:
    body: dict[str, object] = {
        "registration_number": user.registration_number,
        "password": SEEDED_PASSWORD,
    }
    if portal is not None:
        body["portal"] = portal
    return client.post("/api/v1/auth/login", json=body).status_code


# ------------------------------------------------------------------ portals


def test_an_admin_signs_in_at_the_administration_entrance(client: TestClient, world: World) -> None:
    assert _login(client, world.admin, "admin") == 200


@pytest.mark.parametrize("role_name", ["student", "faculty", "coordinator"])
def test_nobody_else_may_use_the_administration_entrance(
    client: TestClient, world: World, role_name: str
) -> None:
    actor: SeededUser = getattr(world, role_name)

    assert _login(client, actor, "admin") == 403


def test_an_admin_may_not_use_the_main_entrance(client: TestClient, world: World) -> None:
    """The console is where their tools are; the dashboard is not."""
    assert _login(client, world.admin, "main") == 403


@pytest.mark.parametrize("role_name", ["student", "faculty", "coordinator"])
def test_everyone_else_uses_the_main_entrance(
    client: TestClient, world: World, role_name: str
) -> None:
    actor: SeededUser = getattr(world, role_name)

    assert _login(client, actor, "main") == 200


def test_a_refused_portal_issues_no_session(client: TestClient, world: World) -> None:
    """403 must mean refused, not "redirected but logged in anyway"."""
    response = client.post(
        "/api/v1/auth/login",
        json={
            "registration_number": world.student.registration_number,
            "password": SEEDED_PASSWORD,
            "portal": "admin",
        },
    )

    assert response.status_code == 403
    assert "access_token" not in response.json()
    assert response.cookies.get("refresh_token") is None


def test_the_portal_check_runs_after_the_password(client: TestClient, world: World) -> None:
    """Otherwise the admin page becomes an oracle: a wrong password on an
    admin account would answer differently from a wrong password on a
    student's, telling an attacker which numbers are administrators."""
    response = client.post(
        "/api/v1/auth/login",
        json={
            "registration_number": world.student.registration_number,
            "password": "definitely-not-the-password",
            "portal": "admin",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Incorrect registration number or password."


def test_omitting_the_portal_still_works(client: TestClient, world: World) -> None:
    """An API client, or a cached older build, is not locked out by a field it
    has never heard of."""
    assert _login(client, world.admin, None) == 200
    assert _login(client, world.student, None) == 200


# ------------------------------------------------------- coordinator scope


def test_promoting_someone_to_coordinator_gives_them_their_department(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    member = seed_user(UserRole.FACULTY, department_id=world.department_id)

    response = client.post(
        f"/api/v1/admin/users/{member.id}/role",
        headers=auth(world.admin),
        json={"role": "research_coordinator"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["coordinator_scope_type"] == CoordinatorScopeType.DEPARTMENT.value
    assert body["coordinator_scope_id"] == str(world.department_id)


def test_a_promoted_coordinator_can_actually_verify(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """The bug as it was reported: coordinators could not verify anyone, only
    the administrator could."""
    new_coordinator = seed_user(UserRole.FACULTY, department_id=world.department_id)
    client.post(
        f"/api/v1/admin/users/{new_coordinator.id}/role",
        headers=auth(world.admin),
        json={"role": "research_coordinator"},
    )

    # Someone waiting to be verified in that department.
    candidate = seed_user(UserRole.FACULTY, department_id=world.department_id)
    client.put(
        "/api/v1/me/profile",
        headers=auth(candidate),
        json={"designation": "Assistant Professor"},
    )

    queue = client.get("/api/v1/coordinator/verification-queue", headers=auth(new_coordinator))
    assert queue.status_code == 200
    assert str(candidate.id) in [row["user_id"] for row in queue.json()]

    decided = client.post(
        f"/api/v1/researchers/{candidate.id}/verify",
        headers=auth(new_coordinator),
        json={"decision": "verified"},
    )
    assert decided.status_code == 200, decided.json()


def test_moving_a_coordinator_moves_what_they_oversee(client: TestClient, world: World) -> None:
    school_id = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Science"}
    ).json()["id"]
    other_department = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": school_id, "name": "Physics"},
    ).json()["id"]

    response = client.patch(
        f"/api/v1/admin/users/{world.coordinator.id}",
        headers=auth(world.admin),
        json={"department_id": other_department},
    )

    assert response.status_code == 200
    assert response.json()["coordinator_scope_id"] == other_department


def test_demoting_a_coordinator_takes_the_scope_away(client: TestClient, world: World) -> None:
    response = client.post(
        f"/api/v1/admin/users/{world.coordinator.id}/role",
        headers=auth(world.admin),
        json={"role": "faculty"},
    )

    assert response.status_code == 200
    assert response.json()["coordinator_scope_id"] is None
    assert response.json()["coordinator_scope_type"] is None


def test_an_explicit_scope_still_wins(client: TestClient, world: World) -> None:
    """Setting the scope directly remains possible, for a coordinator whose
    authority is deliberately not their own department."""
    school_id = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Arts"}
    ).json()["id"]
    other_department = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": school_id, "name": "History"},
    ).json()["id"]

    response = client.patch(
        f"/api/v1/admin/users/{world.coordinator.id}",
        headers=auth(world.admin),
        json={
            "department_id": world.department_id,
            "coordinator_scope_type": "department",
            "coordinator_scope_id": other_department,
        },
    )

    assert response.status_code == 200
    assert response.json()["coordinator_scope_id"] == other_department


# --------------------------------------------------- the UID, everywhere


def test_a_researcher_card_carries_the_registration_number(
    client: TestClient, world: World
) -> None:
    body = client.get("/api/v1/researchers", headers=auth(world.student)).json()

    assert body["items"], "the world seeds verified researchers"
    assert all(item["registration_number"] for item in body["items"])


def test_researchers_can_be_found_by_registration_number(client: TestClient, world: World) -> None:
    number = world.faculty.registration_number

    body = client.get(
        "/api/v1/researchers", headers=auth(world.student), params={"q": number}
    ).json()

    assert str(world.faculty.id) in [item["user_id"] for item in body["items"]]


def test_students_can_be_found_by_registration_number(client: TestClient, world: World) -> None:
    number = world.student.registration_number

    body = client.get("/api/v1/students", headers=auth(world.faculty), params={"q": number}).json()

    assert [item["registration_number"] for item in body["items"]] == [number]


def test_searching_by_number_is_case_insensitive(client: TestClient, world: World) -> None:
    body = client.get(
        "/api/v1/students",
        headers=auth(world.faculty),
        params={"q": world.student.registration_number.lower()},
    ).json()

    assert body["items"], "a number typed in lower case is the same number"
