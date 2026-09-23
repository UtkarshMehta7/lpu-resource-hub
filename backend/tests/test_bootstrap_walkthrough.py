"""From an empty database to a working student, with no shortcuts.

Every deadlock this platform has hit was a bootstrapping gap: an endpoint
existed but no page reached it, or a rule was right but nobody was left who
could satisfy it. A matrix of permission tests never catches that, because
each one starts from a world someone else already built.

So this walks the whole chain in order, using only HTTP calls a real person
could make from the UI, starting from nothing but the first admin (which
scripts/create_admin.py creates, and `seed_user` stands in for here).

If this test fails, a fresh install is unusable, whatever else passes.
"""

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


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _sign_in(client: TestClient, registration_number: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"registration_number": registration_number, "password": password},
    )
    assert response.status_code == 200, response.json()
    token: str = response.json()["access_token"]
    return token


def _replace_temporary_password(client: TestClient, token: str, old: str, new: str) -> None:
    changed = client.post(
        "/api/v1/auth/change-password",
        headers=_auth(token),
        json={"current_password": old, "new_password": new},
    )
    assert changed.status_code == 204, changed.json()


def test_an_empty_platform_can_be_brought_all_the_way_up(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    # --- 0. The only thing that exists is the first admin -----------------
    admin = seed_user(UserRole.ADMIN)
    admin_headers = {"Authorization": f"Bearer {admin.access_token}"}

    assert client.get("/api/v1/schools", headers=admin_headers).json() == []
    assert client.get("/api/v1/departments", headers=admin_headers).json() == []

    # --- 1. The admin builds the organisation ----------------------------
    school = client.post(
        "/api/v1/admin/schools", headers=admin_headers, json={"name": "School of Engineering"}
    )
    assert school.status_code == 201, school.json()
    department = client.post(
        "/api/v1/admin/departments",
        headers=admin_headers,
        json={"school_id": school.json()["id"], "name": "Computer Science"},
    )
    assert department.status_code == 201, department.json()
    department_id = department.json()["id"]

    # --- 2. The admin appoints a coordinator for it ----------------------
    appointed = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "registration_number": "BOOTCOORD1",
            "full_name": "First Coordinator",
            "department_id": department_id,
        },
    )
    assert appointed.status_code == 201, appointed.json()
    coordinator = appointed.json()["user"]
    assert coordinator["role"] == "research_coordinator"
    # Appointed to oversee the department, so they can work immediately.
    assert coordinator["coordinator_scope_id"] == department_id

    coordinator_token = _sign_in(client, "BOOTCOORD1", appointed.json()["temporary_password"])
    _replace_temporary_password(
        client, coordinator_token, appointed.json()["temporary_password"], "coordinator-pass-1"
    )
    coordinator_token = _sign_in(client, "BOOTCOORD1", "coordinator-pass-1")

    # --- 3. The coordinator appoints a faculty member --------------------
    faculty_created = client.post(
        "/api/v1/users",
        headers=_auth(coordinator_token),
        json={"registration_number": "BOOTFAC001", "full_name": "First Faculty"},
    )
    assert faculty_created.status_code == 201, faculty_created.json()
    faculty = faculty_created.json()["user"]
    assert faculty["role"] == "faculty"
    assert faculty["department_id"] == department_id

    faculty_token = _sign_in(client, "BOOTFAC001", faculty_created.json()["temporary_password"])
    _replace_temporary_password(
        client, faculty_token, faculty_created.json()["temporary_password"], "faculty-pass-1"
    )
    faculty_token = _sign_in(client, "BOOTFAC001", "faculty-pass-1")

    # --- 4. Unverified, the faculty member cannot enrol anyone yet -------
    blocked = client.post(
        "/api/v1/users",
        headers=_auth(faculty_token),
        json={"registration_number": "BOOTSTU001", "full_name": "First Student"},
    )
    assert blocked.status_code == 403
    message = blocked.json()["error"]["message"]
    # The message has to name a way out, not just the rule.
    assert "coordinator" in message and "administrator" in message

    # --- 5. They submit a profile, and the coordinator verifies it -------
    profile = client.put(
        "/api/v1/me/profile",
        headers=_auth(faculty_token),
        json={"designation": "Assistant Professor", "bio": "Sensing and instrumentation."},
    )
    assert profile.status_code == 200, profile.json()

    queue = client.get("/api/v1/coordinator/verification-queue", headers=_auth(coordinator_token))
    assert queue.status_code == 200
    assert [row["user_id"] for row in queue.json()] == [faculty["id"]]

    verified = client.post(
        f"/api/v1/researchers/{faculty['id']}/verify",
        headers=_auth(coordinator_token),
        json={"decision": "verified"},
    )
    assert verified.status_code == 200, verified.json()

    # --- 6. Now they can enrol a student ---------------------------------
    student_created = client.post(
        "/api/v1/users",
        headers=_auth(faculty_token),
        json={"registration_number": "BOOTSTU001", "full_name": "First Student"},
    )
    assert student_created.status_code == 201, student_created.json()
    student = student_created.json()["user"]
    assert student["role"] == "student"
    assert student["department_id"] == department_id

    # --- 7. And the student can actually use the platform ----------------
    student_token = _sign_in(client, "BOOTSTU001", student_created.json()["temporary_password"])
    _replace_temporary_password(
        client, student_token, student_created.json()["temporary_password"], "student-pass-1"
    )
    student_token = _sign_in(client, "BOOTSTU001", "student-pass-1")

    me = client.get("/api/v1/me", headers=_auth(student_token))
    assert me.status_code == 200
    assert me.json()["must_change_password"] is False
    # Not walled off any more: an ordinary page answers.
    assert client.get("/api/v1/opportunities", headers=_auth(student_token)).status_code == 200


def test_an_admin_can_unblock_a_department_with_no_coordinator(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    """The deadlock that actually happened.

    A faculty member sits in a department that has no coordinator, so the
    rule "a coordinator must verify you" leaves nobody who can. An admin has
    to be able to do it, or the account is stuck forever.
    """
    admin = seed_user(UserRole.ADMIN)
    admin_headers = {"Authorization": f"Bearer {admin.access_token}"}
    school_id = client.post(
        "/api/v1/admin/schools", headers=admin_headers, json={"name": "Orphan School"}
    ).json()["id"]
    department_id = client.post(
        "/api/v1/admin/departments",
        headers=admin_headers,
        json={"school_id": school_id, "name": "Unstaffed Department"},
    ).json()["id"]

    # A faculty member with no coordinator above them.
    stranded = seed_user(UserRole.FACULTY, department_id=department_id)
    stranded_headers = {"Authorization": f"Bearer {stranded.access_token}"}
    client.put(
        "/api/v1/me/profile",
        headers=stranded_headers,
        json={"designation": "Professor"},
    )

    # The admin sees them in the queue -- unfiltered, unlike a coordinator.
    queue = client.get("/api/v1/coordinator/verification-queue", headers=admin_headers)
    assert queue.status_code == 200
    assert str(stranded.id) in [row["user_id"] for row in queue.json()]

    verified = client.post(
        f"/api/v1/researchers/{stranded.id}/verify",
        headers=admin_headers,
        json={"decision": "verified"},
    )
    assert verified.status_code == 200, verified.json()

    # ...and they are unstuck.
    created = client.post(
        "/api/v1/users",
        headers=stranded_headers,
        json={"registration_number": "UNSTUCK001", "full_name": "Finally Possible"},
    )
    assert created.status_code == 201, created.json()


def test_a_faculty_member_with_no_department_is_told_what_to_do(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    """Self-registered accounts predate the hierarchy and have no department."""
    stranded = seed_user(UserRole.FACULTY)

    response = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {stranded.access_token}"},
        json={"registration_number": "NOWHERE001", "full_name": "Nobody"},
    )

    assert response.status_code == 403
    message = response.json()["error"]["message"]
    assert "department" in message
    # Names the next action, not only the rule.
    assert "profile" in message or "administrator" in message
