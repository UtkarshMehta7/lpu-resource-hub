"""Who decides which department someone belongs to, and what that unlocks.

A self-registered faculty member starts with no department at all, which is
what made "Add a person" unusable for them. They may now state one -- but a
stated department is only a claim until a coordinator verifies the profile,
so it can't by itself become permission to create accounts there.
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


def _save_researcher_profile(
    client: TestClient, user: SeededUser, **extra: object
) -> tuple[int, dict[str, object]]:
    response = client.put(
        "/api/v1/me/profile",
        headers=auth(user),
        json={"designation": "Assistant Professor", **extra},
    )
    return response.status_code, response.json()


# --------------------------------------------------------------- self-service


def test_a_faculty_member_can_state_their_own_department(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """The case that was stuck: self-registered, so no department at all."""
    newcomer = seed_user(UserRole.FACULTY)
    assert client.get("/api/v1/me", headers=auth(newcomer)).json()["department_id"] is None

    code, body = _save_researcher_profile(client, newcomer, department_id=world.department_id)

    assert code == 200, body
    assert body["department_id"] == world.department_id
    assert body["department_locked"] is False
    assert (
        client.get("/api/v1/me", headers=auth(newcomer)).json()["department_id"]
        == world.department_id
    )


def test_a_student_can_state_their_own_department(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    student = seed_user(UserRole.STUDENT)

    response = client.put(
        "/api/v1/me/profile",
        headers=auth(student),
        json={"program": "B.Tech", "year": 2, "department_id": world.department_id},
    )

    assert response.status_code == 200
    assert response.json()["department_id"] == world.department_id
    # Nothing a student can do is department-scoped, so it never locks.
    assert response.json()["department_locked"] is False


def test_a_department_that_does_not_exist_is_404(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    newcomer = seed_user(UserRole.FACULTY)

    code, _ = _save_researcher_profile(
        client, newcomer, department_id="11111111-1111-1111-1111-111111111111"
    )

    assert code == 404


def test_leaving_department_out_of_the_body_keeps_the_current_one(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    newcomer = seed_user(UserRole.FACULTY, department_id=world.department_id)

    code, body = _save_researcher_profile(client, newcomer, bio="Edited my bio only.")

    assert code == 200
    assert body["department_id"] == world.department_id


# ------------------------------------------------------------------- the lock


def test_a_verified_researcher_cannot_move_themselves(client: TestClient, world: World) -> None:
    """world.faculty is verified, so their department is now the record."""
    other_school = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Science School"}
    ).json()["id"]
    other_department = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": other_school, "name": "Chemistry"},
    ).json()["id"]

    code, _ = _save_researcher_profile(client, world.faculty, department_id=other_department)

    assert code == 409
    assert client.get("/api/v1/me", headers=auth(world.faculty)).json()["department_id"] == str(
        world.department_id
    )


def test_a_verified_profile_reports_its_department_as_locked(
    client: TestClient, world: World
) -> None:
    body = client.get("/api/v1/me/profile", headers=auth(world.faculty)).json()

    assert body["department_locked"] is True
    assert body["department_id"] == str(world.department_id)


# ------------------------------------------------- what a department unlocks


def test_an_unverified_faculty_member_cannot_create_accounts_in_a_claimed_department(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """The escalation this rule exists to close: claim a department, then
    start making accounts in it."""
    newcomer = seed_user(UserRole.FACULTY)
    _save_researcher_profile(client, newcomer, department_id=world.department_id)

    response = client.post(
        "/api/v1/users",
        headers=auth(newcomer),
        json={"registration_number": "44445555", "full_name": "Would Be Student"},
    )

    assert response.status_code == 403
    assert "verify" in response.json()["error"]["message"]


def test_verification_is_what_unlocks_adding_people(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    newcomer = seed_user(UserRole.FACULTY)
    _save_researcher_profile(client, newcomer, department_id=world.department_id)
    client.post(
        f"/api/v1/researchers/{newcomer.id}/verify",
        headers=auth(world.admin),
        json={"decision": "verified"},
    )

    response = client.post(
        "/api/v1/users",
        headers=auth(newcomer),
        json={"registration_number": "44445555", "full_name": "Real Student"},
    )

    assert response.status_code == 201, response.json()


def test_a_coordinator_without_a_scope_cannot_add_people(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """A coordinator's authority is the scope an admin gave them, not the
    department they happen to sit in."""
    unscoped = seed_user(UserRole.RESEARCH_COORDINATOR, department_id=world.department_id)

    response = client.post(
        "/api/v1/users",
        headers=auth(unscoped),
        json={"registration_number": "66667777", "full_name": "Nobody"},
    )

    assert response.status_code == 403


def test_a_scoped_coordinator_still_adds_people(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/users",
        headers=auth(world.coordinator),
        json={"registration_number": "88889999", "full_name": "Coordinator Made"},
    )

    assert response.status_code == 201, response.json()


# ------------------------------------------------------------ the admin route


def test_an_admin_places_someone_in_a_department_and_it_is_audited(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    stranded = seed_user(UserRole.FACULTY)

    response = client.patch(
        f"/api/v1/admin/users/{stranded.id}",
        headers=auth(world.admin),
        json={"department_id": world.department_id},
    )

    assert response.status_code == 200
    assert response.json()["department_id"] == world.department_id

    logs = client.get(
        "/api/v1/admin/audit-logs",
        headers=auth(world.admin),
        params={"action": "user.department_changed", "entity_id": str(stranded.id)},
    ).json()["items"]
    assert len(logs) == 1
    assert logs[0]["before"] == {"department_id": None}
    assert logs[0]["after"] == {"department_id": world.department_id}
    assert logs[0]["actor_id"] == str(world.admin.id)


def test_an_admin_can_move_even_a_verified_researcher(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """What the lock leaves open: the institution can still correct itself."""
    response = client.patch(
        f"/api/v1/admin/users/{world.faculty.id}",
        headers=auth(world.admin),
        json={"department_id": None},
    )

    assert response.status_code == 200
    assert response.json()["department_id"] is None


def test_an_unknown_department_is_rejected(client: TestClient, world: World) -> None:
    response = client.patch(
        f"/api/v1/admin/users/{world.faculty.id}",
        headers=auth(world.admin),
        json={"department_id": "11111111-1111-1111-1111-111111111111"},
    )

    assert response.status_code == 422


def test_a_patch_that_omits_department_leaves_it_alone(client: TestClient, world: World) -> None:
    response = client.patch(
        f"/api/v1/admin/users/{world.faculty.id}",
        headers=auth(world.admin),
        json={"full_name": "Renamed Person"},
    )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Renamed Person"
    assert response.json()["department_id"] == str(world.department_id)


def test_only_an_admin_may_place_people(client: TestClient, world: World) -> None:
    response = client.patch(
        f"/api/v1/admin/users/{world.student.id}",
        headers=auth(world.coordinator),
        json={"department_id": world.department_id},
    )

    assert response.status_code == 403


def test_coordinator_scope_still_validates_independently(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)

    response = client.patch(
        f"/api/v1/admin/users/{coordinator.id}",
        headers=auth(world.admin),
        json={
            "department_id": world.department_id,
            "coordinator_scope_type": CoordinatorScopeType.DEPARTMENT.value,
            "coordinator_scope_id": world.department_id,
        },
    )

    assert response.status_code == 200
    assert response.json()["coordinator_scope_id"] == world.department_id
