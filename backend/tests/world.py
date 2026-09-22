"""A small populated world shared by the Step 10 test modules.

Earlier steps build their own fixtures inline; by Step 10 the dashboard and
saved-item tests need most of the platform at once (department, verified
faculty, an active project, an open opportunity, an application), so the
setup lives here instead of being written out three times.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.modules.users.models import CoordinatorScopeType, UserRole
from tests.conftest import SeededUser

TOMORROW = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()


def auth(user: SeededUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.access_token}"}


@dataclass
class World:
    admin: SeededUser
    coordinator: SeededUser
    faculty: SeededUser
    other_faculty: SeededUser
    student: SeededUser
    other_student: SeededUser
    department_id: str
    project_id: str
    opportunity_id: str
    draft_project_id: str


def build_world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    admin = seed_user(UserRole.ADMIN)
    school_id = client.post(
        "/api/v1/admin/schools", headers=auth(admin), json={"name": "Engineering School"}
    ).json()["id"]
    department_id = client.post(
        "/api/v1/admin/departments",
        headers=auth(admin),
        json={"school_id": school_id, "name": "Agriculture"},
    ).json()["id"]
    coordinator = seed_user(
        UserRole.RESEARCH_COORDINATOR,
        department_id=department_id,
        coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
        coordinator_scope_id=department_id,
    )

    def verified_faculty() -> SeededUser:
        user = seed_user(UserRole.FACULTY, department_id=department_id)
        client.put(
            "/api/v1/me/profile",
            headers=auth(user),
            json={"designation": "Professor", "bio": "Soil moisture sensing for farms."},
        )
        client.post(
            f"/api/v1/researchers/{user.id}/verify",
            headers=auth(admin),
            json={"decision": "verified"},
        )
        return user

    faculty = verified_faculty()
    other_faculty = verified_faculty()

    project_id = client.post(
        "/api/v1/projects",
        headers=auth(faculty),
        json={
            "title": "Low-cost soil sensors",
            "summary": "Cheap sensors for farms.",
            "description": "We build and field-test low-cost soil moisture sensors.",
        },
    ).json()["id"]
    client.post(f"/api/v1/projects/{project_id}/submit", headers=auth(faculty))
    client.post(
        f"/api/v1/projects/{project_id}/review",
        headers=auth(coordinator),
        json={"decision": "approve"},
    )
    draft_project_id = client.post(
        "/api/v1/projects",
        headers=auth(other_faculty),
        json={"title": "Unpublished work", "summary": "S", "description": "D"},
    ).json()["id"]

    opportunity_id = client.post(
        "/api/v1/opportunities",
        headers=auth(faculty),
        json={
            "title": "Field assistant for soil sensors",
            "description": "Help calibrate sensors during field trials.",
            "opportunity_type": "research_assistant",
            "project_id": project_id,
            "positions": 2,
            "deadline": TOMORROW,
        },
    ).json()["id"]
    client.post(f"/api/v1/opportunities/{opportunity_id}/publish", headers=auth(faculty))

    def student(discoverable: bool) -> SeededUser:
        user = seed_user(UserRole.STUDENT, department_id=department_id)
        client.put(
            "/api/v1/me/profile",
            headers=auth(user),
            json={"program": "B.Tech", "year": 3, "is_discoverable": discoverable},
        )
        return user

    return World(
        admin=admin,
        coordinator=coordinator,
        faculty=faculty,
        other_faculty=other_faculty,
        student=student(True),
        other_student=student(False),
        department_id=department_id,
        project_id=project_id,
        opportunity_id=opportunity_id,
        draft_project_id=draft_project_id,
    )
