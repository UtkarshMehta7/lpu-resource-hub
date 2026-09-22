"""Research project workflow, visibility and ownership tests (real PostgreSQL)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.users.models import CoordinatorScopeType, UserRole
from tests.conftest import SeededUser

pytestmark = pytest.mark.db

PROJECT_BODY = {
    "title": "Low-cost soil sensors",
    "summary": "Cheap IoT sensors for smallholder farms.",
    "description": "We build and field-test low-cost soil moisture sensors.",
}


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


def _auth(user: SeededUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.access_token}"}


@dataclass
class World:
    admin: SeededUser
    dept_a: str
    dept_b: str
    coordinator_a: SeededUser
    coordinator_b: SeededUser
    owner: SeededUser  # verified faculty in dept A
    other_faculty: SeededUser  # verified faculty in dept A
    student: SeededUser


def _department(client: TestClient, admin: SeededUser, name: str) -> str:
    school_id = client.post(
        "/api/v1/admin/schools", headers=_auth(admin), json={"name": f"{name} School"}
    ).json()["id"]
    department_id: str = client.post(
        "/api/v1/admin/departments",
        headers=_auth(admin),
        json={"school_id": school_id, "name": name},
    ).json()["id"]
    return department_id


def _verified_faculty(
    client: TestClient, seed_user: Callable[..., SeededUser], admin: SeededUser, dept: str
) -> SeededUser:
    faculty = seed_user(UserRole.FACULTY, department_id=dept)
    client.put(
        "/api/v1/me/profile", headers=_auth(faculty), json={"designation": "Assistant Professor"}
    )
    client.post(
        f"/api/v1/researchers/{faculty.id}/verify",
        headers=_auth(admin),
        json={"decision": "verified"},
    )
    return faculty


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    admin = seed_user(UserRole.ADMIN)
    dept_a = _department(client, admin, "Agriculture")
    dept_b = _department(client, admin, "Chemistry")

    def coordinator(dept: str) -> SeededUser:
        return seed_user(
            UserRole.RESEARCH_COORDINATOR,
            department_id=dept,
            coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
            coordinator_scope_id=dept,
        )

    return World(
        admin=admin,
        dept_a=dept_a,
        dept_b=dept_b,
        coordinator_a=coordinator(dept_a),
        coordinator_b=coordinator(dept_b),
        owner=_verified_faculty(client, seed_user, admin, dept_a),
        other_faculty=_verified_faculty(client, seed_user, admin, dept_a),
        student=seed_user(UserRole.STUDENT, department_id=dept_a),
    )


def _create(client: TestClient, owner: SeededUser, **overrides: object) -> str:
    response = client.post(
        "/api/v1/projects", headers=_auth(owner), json={**PROJECT_BODY, **overrides}
    )
    assert response.status_code == 201, response.text
    project_id: str = response.json()["id"]
    return project_id


def _active_project(client: TestClient, world: World) -> str:
    project_id = _create(client, world.owner)
    client.post(f"/api/v1/projects/{project_id}/submit", headers=_auth(world.owner))
    client.post(
        f"/api/v1/projects/{project_id}/review",
        headers=_auth(world.coordinator_a),
        json={"decision": "approve"},
    )
    return project_id


def test_full_workflow_draft_to_completed(client: TestClient, world: World) -> None:
    project_id = _create(client, world.owner)
    assert (
        client.get(f"/api/v1/projects/{project_id}", headers=_auth(world.owner)).json()["status"]
        == "draft"
    )

    submitted = client.post(f"/api/v1/projects/{project_id}/submit", headers=_auth(world.owner))
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "pending_review"

    queue = client.get("/api/v1/coordinator/review-queue", headers=_auth(world.coordinator_a))
    assert [p["id"] for p in queue.json()] == [project_id]

    approved = client.post(
        f"/api/v1/projects/{project_id}/review",
        headers=_auth(world.coordinator_a),
        json={"decision": "approve", "comment": "Looks good."},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "active"

    completed = client.post(f"/api/v1/projects/{project_id}/complete", headers=_auth(world.owner))
    assert completed.json()["status"] == "completed"


def test_reject_requires_a_comment_and_returns_to_draft(client: TestClient, world: World) -> None:
    project_id = _create(client, world.owner)
    client.post(f"/api/v1/projects/{project_id}/submit", headers=_auth(world.owner))

    no_comment = client.post(
        f"/api/v1/projects/{project_id}/review",
        headers=_auth(world.coordinator_a),
        json={"decision": "reject"},
    )
    assert no_comment.status_code == 422

    rejected = client.post(
        f"/api/v1/projects/{project_id}/review",
        headers=_auth(world.coordinator_a),
        json={"decision": "reject", "comment": "Needs a methodology section."},
    )
    assert rejected.status_code == 200
    body = rejected.json()
    assert body["status"] == "draft"
    assert body["review_comment"] == "Needs a methodology section."


def test_unverified_faculty_cannot_submit(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    unverified = seed_user(UserRole.FACULTY, department_id=world.dept_a)
    project_id = _create(client, unverified)

    response = client.post(f"/api/v1/projects/{project_id}/submit", headers=_auth(unverified))

    assert response.status_code == 403


def test_student_cannot_create_a_project(client: TestClient, world: World) -> None:
    response = client.post("/api/v1/projects", headers=_auth(world.student), json=PROJECT_BODY)

    assert response.status_code == 403


def test_coordinator_cannot_review_another_departments_project(
    client: TestClient, world: World
) -> None:
    project_id = _create(client, world.owner)
    client.post(f"/api/v1/projects/{project_id}/submit", headers=_auth(world.owner))

    response = client.post(
        f"/api/v1/projects/{project_id}/review",
        headers=_auth(world.coordinator_b),
        json={"decision": "approve"},
    )

    assert response.status_code == 404


def test_coordinator_cannot_review_their_own_project(client: TestClient, world: World) -> None:
    client.put(
        "/api/v1/me/profile",
        headers=_auth(world.coordinator_a),
        json={"designation": "Professor"},
    )
    client.post(
        f"/api/v1/researchers/{world.coordinator_a.id}/verify",
        headers=_auth(world.admin),
        json={"decision": "verified"},
    )
    project_id = _create(client, world.coordinator_a)
    client.post(f"/api/v1/projects/{project_id}/submit", headers=_auth(world.coordinator_a))

    response = client.post(
        f"/api/v1/projects/{project_id}/review",
        headers=_auth(world.coordinator_a),
        json={"decision": "approve"},
    )

    assert response.status_code == 403


def test_other_faculty_cannot_edit_a_visible_project(client: TestClient, world: World) -> None:
    project_id = _active_project(client, world)

    response = client.patch(
        f"/api/v1/projects/{project_id}",
        headers=_auth(world.other_faculty),
        json={"title": "Hijacked"},
    )

    assert response.status_code == 403


def test_student_sees_404_for_a_draft_but_can_see_active(client: TestClient, world: World) -> None:
    draft_id = _create(client, world.owner)
    active_id = _active_project(client, world)

    assert (
        client.get(f"/api/v1/projects/{draft_id}", headers=_auth(world.student)).status_code == 404
    )
    assert (
        client.get(f"/api/v1/projects/{active_id}", headers=_auth(world.student)).status_code == 200
    )

    listed = client.get("/api/v1/projects", headers=_auth(world.student)).json()
    assert [p["id"] for p in listed["items"]] == [active_id]


def test_scoped_coordinator_can_see_drafts_in_their_department(
    client: TestClient, world: World
) -> None:
    draft_id = _create(client, world.owner)

    assert (
        client.get(f"/api/v1/projects/{draft_id}", headers=_auth(world.coordinator_a)).status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/projects/{draft_id}", headers=_auth(world.coordinator_b)).status_code
        == 404
    )


def test_invalid_transitions_return_409(client: TestClient, world: World) -> None:
    project_id = _create(client, world.owner)

    # Can't complete a draft, and can't review something not pending.
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/complete", headers=_auth(world.owner)
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/review",
            headers=_auth(world.coordinator_a),
            json={"decision": "approve"},
        ).status_code
        == 409
    )

    # Can't edit while under review.
    client.post(f"/api/v1/projects/{project_id}/submit", headers=_auth(world.owner))
    assert (
        client.patch(
            f"/api/v1/projects/{project_id}", headers=_auth(world.owner), json={"title": "x"}
        ).status_code
        == 409
    )


def test_delete_soft_deletes_a_draft_and_archives_anything_else(
    client: TestClient, world: World
) -> None:
    draft_id = _create(client, world.owner)
    assert (
        client.delete(f"/api/v1/projects/{draft_id}", headers=_auth(world.owner)).status_code == 204
    )
    assert client.get(f"/api/v1/projects/{draft_id}", headers=_auth(world.owner)).status_code == 404

    active_id = _active_project(client, world)
    assert (
        client.delete(f"/api/v1/projects/{active_id}", headers=_auth(world.owner)).status_code
        == 204
    )
    assert (
        client.get(f"/api/v1/projects/{active_id}", headers=_auth(world.owner)).json()["status"]
        == "archived"
    )


def test_admin_can_archive_any_project_and_it_is_audited(client: TestClient, world: World) -> None:
    project_id = _create(client, world.owner)

    response = client.post(f"/api/v1/projects/{project_id}/archive", headers=_auth(world.admin))
    assert response.status_code == 200
    assert response.json()["status"] == "archived"

    logs = client.get(
        "/api/v1/admin/audit-logs",
        params={"entity_id": project_id, "action": "project.archived"},
        headers=_auth(world.admin),
    ).json()["items"]
    assert len(logs) == 1


def test_review_decisions_are_audited(client: TestClient, world: World) -> None:
    project_id = _active_project(client, world)

    logs = client.get(
        "/api/v1/admin/audit-logs",
        params={"entity_id": project_id, "action": "project.approved"},
        headers=_auth(world.admin),
    ).json()["items"]
    assert len(logs) == 1
    assert logs[0]["before"] == {"status": "pending_review"}


def test_members_can_be_added_and_removed_by_the_owner_only(
    client: TestClient, world: World
) -> None:
    project_id = _active_project(client, world)

    added = client.post(
        f"/api/v1/projects/{project_id}/members",
        headers=_auth(world.owner),
        json={"user_id": str(world.student.id), "member_role": "Research assistant"},
    )
    assert added.status_code == 201
    assert [m["user_id"] for m in added.json()] == [str(world.student.id)]

    duplicate = client.post(
        f"/api/v1/projects/{project_id}/members",
        headers=_auth(world.owner),
        json={"user_id": str(world.student.id), "member_role": "Again"},
    )
    assert duplicate.status_code == 409

    not_owner = client.delete(
        f"/api/v1/projects/{project_id}/members/{world.student.id}",
        headers=_auth(world.other_faculty),
    )
    assert not_owner.status_code == 403

    removed = client.delete(
        f"/api/v1/projects/{project_id}/members/{world.student.id}",
        headers=_auth(world.owner),
    )
    assert removed.status_code == 204


def test_a_member_can_see_a_draft_they_belong_to(client: TestClient, world: World) -> None:
    project_id = _create(client, world.owner)
    client.post(
        f"/api/v1/projects/{project_id}/members",
        headers=_auth(world.owner),
        json={"user_id": str(world.student.id), "member_role": "Assistant"},
    )

    assert (
        client.get(f"/api/v1/projects/{project_id}", headers=_auth(world.student)).status_code
        == 200
    )


def test_date_range_is_validated(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/projects",
        headers=_auth(world.owner),
        json={**PROJECT_BODY, "start_date": "2026-12-01", "end_date": "2026-01-01"},
    )

    assert response.status_code == 422


def test_projects_are_searchable_and_search_respects_visibility(
    client: TestClient, world: World
) -> None:
    active_id = _active_project(client, world)
    _create(client, world.owner, title="Secret draft about sensors")

    results = client.get(
        "/api/v1/search", params={"q": "sensors"}, headers=_auth(world.student)
    ).json()

    assert [p["id"] for p in results["projects"]] == [active_id]


def test_mine_filter_returns_owned_projects(client: TestClient, world: World) -> None:
    mine = _create(client, world.owner)
    _create(client, world.other_faculty)

    listed = client.get(
        "/api/v1/projects", params={"mine": True}, headers=_auth(world.owner)
    ).json()

    assert [p["id"] for p in listed["items"]] == [mine]
