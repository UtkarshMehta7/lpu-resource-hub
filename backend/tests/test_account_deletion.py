"""Removing an account, down the same hierarchy that creates one.

An administrator may remove anyone but themselves; a coordinator, the faculty
and students of the department they oversee; a faculty member, the students of
theirs; a student, nobody. Deletion is the answer for an account that should
never have existed. Deactivation stays the answer for a person who has left,
because it keeps their work and their name on the decisions they made.

The dangerous part is not the permission -- it is the cascade. Deleting a
faculty member takes their projects with them, and every application to those
projects. So the impact is countable *before* anyone confirms, and these tests
pin what the cascade actually does rather than what it is assumed to do.
"""

from __future__ import annotations

import uuid
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


def _delete(client: TestClient, actor: SeededUser, target_id: uuid.UUID | str) -> int:
    return client.delete(f"/api/v1/users/{target_id}", headers=auth(actor)).status_code


def _exists(client: TestClient, world: World, target_id: uuid.UUID | str) -> bool:
    body = client.get(
        "/api/v1/admin/users", headers=auth(world.admin), params={"page_size": 100}
    ).json()
    return str(target_id) in [item["id"] for item in body["items"]]


# ------------------------------------------------------- who may remove whom


@pytest.mark.parametrize("role_name", ["student", "faculty", "coordinator"])
def test_an_admin_may_remove_anyone(client: TestClient, world: World, role_name: str) -> None:
    target: SeededUser = getattr(world, role_name)

    assert _delete(client, world.admin, target.id) == 204
    assert not _exists(client, world, target.id)


def test_an_admin_may_remove_another_admin(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    other = seed_user(UserRole.ADMIN)

    assert _delete(client, world.admin, other.id) == 204


def test_a_coordinator_may_remove_faculty_and_students_of_their_department(
    client: TestClient, world: World
) -> None:
    assert _delete(client, world.coordinator, world.faculty.id) == 204
    assert _delete(client, world.coordinator, world.student.id) == 204


def test_a_coordinator_may_not_remove_a_coordinator_or_an_admin(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    peer = seed_user(UserRole.RESEARCH_COORDINATOR, department_id=world.department_id)

    assert _delete(client, world.coordinator, peer.id) == 403
    assert _delete(client, world.coordinator, world.admin.id) == 403
    assert _exists(client, world, peer.id)


def test_a_faculty_member_may_remove_a_student_of_their_department(
    client: TestClient, world: World
) -> None:
    assert _delete(client, world.faculty, world.student.id) == 204


def test_a_faculty_member_may_not_remove_faculty(client: TestClient, world: World) -> None:
    assert _delete(client, world.faculty, world.other_faculty.id) == 403


def test_a_student_may_remove_nobody(client: TestClient, world: World) -> None:
    """No permission at all, so it never reaches a scope check."""
    assert _delete(client, world.student, world.other_student.id) == 403


def test_signing_in_is_required(client: TestClient, world: World) -> None:
    assert client.delete(f"/api/v1/users/{world.student.id}").status_code == 401


def test_an_unknown_account_is_404(client: TestClient, world: World) -> None:
    assert _delete(client, world.admin, uuid.uuid4()) == 404


# ------------------------------------------------------------------- scope


def test_a_coordinator_may_not_reach_another_department(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    school_id = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Science"}
    ).json()["id"]
    elsewhere = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": school_id, "name": "Physics"},
    ).json()["id"]
    outsider = seed_user(UserRole.STUDENT, department_id=elsewhere)

    assert _delete(client, world.coordinator, outsider.id) == 403
    assert _exists(client, world, outsider.id)


def test_a_coordinator_with_no_scope_may_remove_nobody(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """The stranded-coordinator case: no scope means no authority, not all of it."""
    stranded = seed_user(UserRole.RESEARCH_COORDINATOR, department_id=world.department_id)

    assert _delete(client, stranded, world.student.id) == 403


def test_an_unverified_faculty_member_may_remove_nobody(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """Faculty declare their own department, so the claim alone is not
    authority over the people in it -- the same rule as creating accounts."""
    unverified = seed_user(UserRole.FACULTY, department_id=world.department_id)

    assert _delete(client, unverified, world.student.id) == 403


def test_a_coordinators_scope_is_what_counts_not_where_they_work(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    school_id = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Arts"}
    ).json()["id"]
    elsewhere = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": school_id, "name": "History"},
    ).json()["id"]
    # Works in Agriculture, oversees History.
    coordinator = seed_user(
        UserRole.RESEARCH_COORDINATOR,
        department_id=world.department_id,
        coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
        coordinator_scope_id=elsewhere,
    )
    theirs = seed_user(UserRole.STUDENT, department_id=elsewhere)

    assert _delete(client, coordinator, world.student.id) == 403, "not their scope"
    assert _delete(client, coordinator, theirs.id) == 204, "their scope"


# --------------------------------------------------------------- guardrails


def test_nobody_deletes_their_own_account(client: TestClient, world: World) -> None:
    assert _delete(client, world.admin, world.admin.id) == 409
    assert _exists(client, world, world.admin.id)


def test_the_platform_can_never_be_left_without_an_administrator(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """Not a separate rule -- a consequence of the two above.

    Only an administrator may delete an administrator, so the last one could
    only ever be deleted by themselves, and that is refused. Here: of two
    admins either may remove the other, and whoever is left cannot remove
    themselves.
    """
    second = seed_user(UserRole.ADMIN)

    assert _delete(client, second, world.admin.id) == 204, "two admins, one may go"
    assert _delete(client, second, second.id) == 409, "the survivor cannot remove themselves"
    assert client.get("/api/v1/admin/users", headers=auth(second)).status_code == 200


# ------------------------------------------------------------ the cascade


def test_the_impact_is_countable_before_confirming(client: TestClient, world: World) -> None:
    response = client.get(
        f"/api/v1/users/{world.faculty.id}/deletion-impact", headers=auth(world.admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["registration_number"] == world.faculty.registration_number
    assert body["full_name"], "the log has to be able to name who was removed"
    assert body["projects_owned"] == 1
    assert body["opportunities_created"] == 1
    assert body["destroys_content"] is True


def test_an_account_that_has_done_nothing_destroys_nothing(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    fresh = seed_user(UserRole.STUDENT, department_id=world.department_id)

    body = client.get(f"/api/v1/users/{fresh.id}/deletion-impact", headers=auth(world.admin)).json()

    assert body["destroys_content"] is False


def test_counting_needs_the_same_authority_as_deleting(client: TestClient, world: World) -> None:
    """Otherwise it would report how much work somebody else has done."""
    response = client.get(
        f"/api/v1/users/{world.admin.id}/deletion-impact", headers=auth(world.coordinator)
    )

    assert response.status_code == 403


def test_deleting_an_owner_takes_their_project_with_them(client: TestClient, world: World) -> None:
    assert _delete(client, world.admin, world.faculty.id) == 204

    remaining = client.get("/api/v1/projects", headers=auth(world.admin)).json()
    assert world.project_id not in [item["id"] for item in remaining["items"]]


def test_the_accounts_they_provisioned_survive(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """Removing a coordinator must not remove the department they built."""
    created = client.post(
        "/api/v1/users",
        headers=auth(world.coordinator),
        json={
            "registration_number": "DEPENDENT01",
            "full_name": "Provisioned Person",
            "department_id": str(world.department_id),
        },
    )
    assert created.status_code == 201, created.json()
    dependent_id = created.json()["user"]["id"]

    assert _delete(client, world.admin, world.coordinator.id) == 204

    assert _exists(client, world, dependent_id)


def test_the_deletion_is_audited_with_who_it_was(client: TestClient, world: World) -> None:
    """The row is gone afterwards, so an id alone would point at nothing."""
    number = world.student.registration_number
    assert _delete(client, world.admin, world.student.id) == 204

    logs = client.get(
        "/api/v1/admin/audit-logs", headers=auth(world.admin), params={"action": "user.deleted"}
    ).json()

    entry = logs["items"][0]
    assert entry["action"] == "user.deleted"
    assert entry["before"]["registration_number"] == number
    assert entry["before"]["role"] == "student"


def test_a_deleted_account_can_no_longer_sign_in(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    target = seed_user(UserRole.STUDENT, department_id=world.department_id)
    assert _delete(client, world.admin, target.id) == 204

    response = client.post(
        "/api/v1/auth/login",
        json={
            "registration_number": target.registration_number,
            "password": "not-used-directly-seeded12",
        },
    )

    assert response.status_code == 401


def test_the_registration_number_is_free_again(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """The point of deleting rather than deactivating a mistyped account: the
    number it took can be used by the account that should have had it."""
    mistyped = seed_user(
        UserRole.STUDENT, registration_number="12400942X", department_id=world.department_id
    )
    assert _delete(client, world.admin, mistyped.id) == 204

    again = client.post(
        "/api/v1/admin/users",
        headers=auth(world.admin),
        json={
            "registration_number": "12400942X",
            "full_name": "The Right Person",
            "department_id": str(world.department_id),
            "role": "student",
        },
    )

    assert again.status_code == 201, again.json()


# ----------------------------------------- the list the buttons live on


def _manageable(client: TestClient, actor: SeededUser) -> list[dict[str, object]]:
    response = client.get("/api/v1/users", headers=auth(actor), params={"page_size": 100})
    assert response.status_code == 200, response.json()
    items: list[dict[str, object]] = response.json()["items"]
    return items


def test_an_admin_is_responsible_for_everyone_but_themselves(
    client: TestClient, world: World
) -> None:
    ids = [item["id"] for item in _manageable(client, world.admin)]

    assert str(world.coordinator.id) in ids
    assert str(world.faculty.id) in ids
    assert str(world.student.id) in ids
    assert str(world.admin.id) not in ids


def test_a_coordinator_sees_the_faculty_and_students_they_oversee(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    school_id = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Science"}
    ).json()["id"]
    elsewhere = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": school_id, "name": "Physics"},
    ).json()["id"]
    outsider = seed_user(UserRole.STUDENT, department_id=elsewhere)

    items = _manageable(client, world.coordinator)
    ids = [item["id"] for item in items]

    assert str(world.faculty.id) in ids
    assert str(world.student.id) in ids
    assert str(outsider.id) not in ids, "another department is not theirs"
    assert str(world.admin.id) not in ids, "nobody above them"


def test_a_faculty_member_sees_only_students(client: TestClient, world: World) -> None:
    roles = {item["role"] for item in _manageable(client, world.faculty)}

    assert roles == {"student"}


def test_a_student_sees_nobody_rather_than_an_error(client: TestClient, world: World) -> None:
    """A student holds no delete permission at all, so the page is refused
    outright rather than showing an empty list -- there is nothing there for
    them to be on."""
    assert client.get("/api/v1/users", headers=auth(world.student)).status_code == 403


def test_a_coordinator_with_no_scope_sees_an_empty_list(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """Not an error: there is genuinely nobody, and saying so is information."""
    stranded = seed_user(UserRole.RESEARCH_COORDINATOR, department_id=world.department_id)

    assert _manageable(client, stranded) == []


def test_every_row_on_the_list_can_actually_be_deleted(client: TestClient, world: World) -> None:
    """The point of the endpoint: the list and the rule agree, so no row shows
    a button that answers 403."""
    for item in _manageable(client, world.coordinator):
        assert _delete(client, world.coordinator, str(item["id"])) == 204


def test_the_decisions_they_made_about_others_survive(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """A verification is a fact about the person verified, not a possession of
    the verifier. Removing the coordinator must not un-verify their
    department, only stop naming who decided."""
    candidate = seed_user(UserRole.FACULTY, department_id=world.department_id)
    client.put(
        "/api/v1/me/profile",
        headers=auth(candidate),
        json={"designation": "Assistant Professor"},
    )
    decided = client.post(
        f"/api/v1/researchers/{candidate.id}/verify",
        headers=auth(world.coordinator),
        json={"decision": "verified"},
    )
    assert decided.status_code == 200, decided.json()

    assert _delete(client, world.admin, world.coordinator.id) == 204

    profile = client.get(f"/api/v1/researchers/{candidate.id}", headers=auth(world.admin))
    assert profile.status_code == 200
    assert profile.json()["verification_status"] == "verified", "still verified"
