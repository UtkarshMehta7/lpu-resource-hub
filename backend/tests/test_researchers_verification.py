"""Researcher verification integration tests against a real PostgreSQL database."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.users.models import CoordinatorScopeType, UserRole
from tests.conftest import SeededUser

pytestmark = pytest.mark.db


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


def _auth_headers(user: SeededUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.access_token}"}


def _create_department(client: TestClient, admin: SeededUser, name: str) -> str:
    school_id = client.post(
        "/api/v1/admin/schools", headers=_auth_headers(admin), json={"name": f"{name} School"}
    ).json()["id"]
    department_id: str = client.post(
        "/api/v1/admin/departments",
        headers=_auth_headers(admin),
        json={"school_id": school_id, "name": name},
    ).json()["id"]
    return department_id


def _submit_researcher_profile(client: TestClient, researcher: SeededUser) -> None:
    response = client.put(
        "/api/v1/me/profile",
        headers=_auth_headers(researcher),
        json={"designation": "Assistant Professor"},
    )
    assert response.status_code == 200
    assert response.json()["verification_status"] == "pending"


def test_queue_requires_the_verify_permission(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    faculty = seed_user(UserRole.FACULTY)
    student = seed_user(UserRole.STUDENT)

    assert (
        client.get(
            "/api/v1/coordinator/verification-queue", headers=_auth_headers(faculty)
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/coordinator/verification-queue", headers=_auth_headers(student)
        ).status_code
        == 403
    )


def test_coordinator_sees_only_their_own_department_in_the_queue(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    dept_a = _create_department(client, admin, "Physics")
    dept_b = _create_department(client, admin, "Chemistry")

    coordinator = seed_user(
        UserRole.RESEARCH_COORDINATOR,
        department_id=dept_a,
        coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
        coordinator_scope_id=dept_a,
    )
    mine = seed_user(UserRole.FACULTY, department_id=dept_a)
    theirs = seed_user(UserRole.FACULTY, department_id=dept_b)
    _submit_researcher_profile(client, mine)
    _submit_researcher_profile(client, theirs)

    response = client.get(
        "/api/v1/coordinator/verification-queue", headers=_auth_headers(coordinator)
    )

    assert response.status_code == 200
    queued_ids = [item["user_id"] for item in response.json()]
    assert queued_ids == [str(mine.id)]


def test_admin_sees_every_department_in_the_queue(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    dept_a = _create_department(client, admin, "Physics")
    dept_b = _create_department(client, admin, "Chemistry")
    first = seed_user(UserRole.FACULTY, department_id=dept_a)
    second = seed_user(UserRole.FACULTY, department_id=dept_b)
    _submit_researcher_profile(client, first)
    _submit_researcher_profile(client, second)

    response = client.get("/api/v1/coordinator/verification-queue", headers=_auth_headers(admin))

    assert response.status_code == 200
    queued_ids = {item["user_id"] for item in response.json()}
    assert queued_ids == {str(first.id), str(second.id)}


def test_coordinator_without_a_scope_sees_an_empty_queue(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    dept = _create_department(client, admin, "Physics")
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)  # no scope assigned
    faculty = seed_user(UserRole.FACULTY, department_id=dept)
    _submit_researcher_profile(client, faculty)

    response = client.get(
        "/api/v1/coordinator/verification-queue", headers=_auth_headers(coordinator)
    )

    assert response.status_code == 200
    assert response.json() == []


def test_coordinator_verifies_a_researcher_in_their_department(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    dept = _create_department(client, admin, "Physics")
    coordinator = seed_user(
        UserRole.RESEARCH_COORDINATOR,
        department_id=dept,
        coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
        coordinator_scope_id=dept,
    )
    faculty = seed_user(UserRole.FACULTY, department_id=dept)
    _submit_researcher_profile(client, faculty)

    response = client.post(
        f"/api/v1/researchers/{faculty.id}/verify",
        headers=_auth_headers(coordinator),
        json={"decision": "verified", "comment": "Checked against department records."},
    )

    assert response.status_code == 200
    assert response.json()["verification_status"] == "verified"

    queue = client.get("/api/v1/coordinator/verification-queue", headers=_auth_headers(coordinator))
    assert queue.json() == []


def test_coordinator_cannot_verify_outside_their_department(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    """404, not 403: they must not learn the profile exists at all."""
    admin = seed_user(UserRole.ADMIN)
    dept_a = _create_department(client, admin, "Physics")
    dept_b = _create_department(client, admin, "Chemistry")
    coordinator = seed_user(
        UserRole.RESEARCH_COORDINATOR,
        department_id=dept_a,
        coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
        coordinator_scope_id=dept_a,
    )
    other_faculty = seed_user(UserRole.FACULTY, department_id=dept_b)
    _submit_researcher_profile(client, other_faculty)

    response = client.post(
        f"/api/v1/researchers/{other_faculty.id}/verify",
        headers=_auth_headers(coordinator),
        json={"decision": "verified"},
    )

    assert response.status_code == 404


def test_coordinator_cannot_verify_their_own_profile(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    dept = _create_department(client, admin, "Physics")
    coordinator = seed_user(
        UserRole.RESEARCH_COORDINATOR,
        department_id=dept,
        coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
        coordinator_scope_id=dept,
    )
    _submit_researcher_profile(client, coordinator)

    response = client.post(
        f"/api/v1/researchers/{coordinator.id}/verify",
        headers=_auth_headers(coordinator),
        json={"decision": "verified"},
    )

    assert response.status_code == 409


def test_admin_can_verify_a_researcher_in_any_department(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    dept = _create_department(client, admin, "Physics")
    faculty = seed_user(UserRole.FACULTY, department_id=dept)
    _submit_researcher_profile(client, faculty)

    response = client.post(
        f"/api/v1/researchers/{faculty.id}/verify",
        headers=_auth_headers(admin),
        json={"decision": "verified"},
    )

    assert response.status_code == 200
    assert response.json()["verification_status"] == "verified"


def test_rejection_is_recorded_and_can_be_resubmitted(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    dept = _create_department(client, admin, "Physics")
    faculty = seed_user(UserRole.FACULTY, department_id=dept)
    _submit_researcher_profile(client, faculty)

    reject_response = client.post(
        f"/api/v1/researchers/{faculty.id}/verify",
        headers=_auth_headers(admin),
        json={"decision": "rejected", "comment": "Designation could not be confirmed."},
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["verification_status"] == "rejected"

    # Editing the profile resubmits it for review.
    resubmit = client.put(
        "/api/v1/me/profile",
        headers=_auth_headers(faculty),
        json={"designation": "Associate Professor"},
    )
    assert resubmit.json()["verification_status"] == "pending"


def test_editing_a_verified_profile_does_not_revoke_verification(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    dept = _create_department(client, admin, "Physics")
    faculty = seed_user(UserRole.FACULTY, department_id=dept)
    _submit_researcher_profile(client, faculty)
    client.post(
        f"/api/v1/researchers/{faculty.id}/verify",
        headers=_auth_headers(admin),
        json={"decision": "verified"},
    )

    response = client.put(
        "/api/v1/me/profile",
        headers=_auth_headers(faculty),
        json={"designation": "Professor", "bio": "Updated bio"},
    )

    assert response.json()["verification_status"] == "verified"


def test_verifying_an_unknown_researcher_is_404(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)

    response = client.post(
        "/api/v1/researchers/11111111-1111-1111-1111-111111111111/verify",
        headers=_auth_headers(admin),
        json={"decision": "verified"},
    )

    assert response.status_code == 404


def test_verification_decision_is_audited(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    dept = _create_department(client, admin, "Physics")
    faculty = seed_user(UserRole.FACULTY, department_id=dept)
    _submit_researcher_profile(client, faculty)

    client.post(
        f"/api/v1/researchers/{faculty.id}/verify",
        headers=_auth_headers(admin),
        json={"decision": "verified", "comment": "Confirmed with the department."},
    )

    audit_response = client.get(
        "/api/v1/admin/audit-logs",
        params={"entity_id": str(faculty.id), "action": "profile.verified"},
        headers=_auth_headers(admin),
    )
    logs = audit_response.json()["items"]
    assert len(logs) == 1
    assert logs[0]["before"] == {"verification_status": "pending"}
    # The reviewer's comment is kept in the audit record: researcher_profiles
    # has no comment column (ADR 0004).
    assert logs[0]["after"] == {
        "verification_status": "verified",
        "comment": "Confirmed with the department.",
    }
    assert logs[0]["actor_id"] == str(admin.id)
