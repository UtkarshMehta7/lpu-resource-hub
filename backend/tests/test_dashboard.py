"""Role dashboards: each role gets its own sections, scoped like its lists."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.ml.tfidf import INDEX_CACHE
from app.modules.users.models import UserRole
from tests.conftest import SeededUser
from tests.world import World, auth, build_world

pytestmark = pytest.mark.db


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    INDEX_CACHE.clear()
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    return build_world(client, seed_user)


def _dashboard(client: TestClient, user: SeededUser) -> dict[str, object]:
    response = client.get("/api/v1/me/dashboard", headers=auth(user))
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_each_role_gets_only_its_own_sections(client: TestClient, world: World) -> None:
    student = _dashboard(client, world.student)
    assert student["role"] == "student"
    assert student["student"] is not None
    assert (student["faculty"], student["coordinator"], student["admin"]) == (None, None, None)

    faculty = _dashboard(client, world.faculty)
    assert faculty["faculty"] is not None
    assert (faculty["student"], faculty["coordinator"], faculty["admin"]) == (None, None, None)

    # Coordinators inherit faculty abilities, so they get both sections.
    coordinator = _dashboard(client, world.coordinator)
    assert coordinator["faculty"] is not None
    assert coordinator["coordinator"] is not None
    assert coordinator["admin"] is None

    admin = _dashboard(client, world.admin)
    assert admin["admin"] is not None
    assert (admin["student"], admin["faculty"], admin["coordinator"]) == (None, None, None)


def test_student_dashboard_tracks_applications_saves_and_deadlines(
    client: TestClient, world: World
) -> None:
    client.post(
        f"/api/v1/opportunities/{world.opportunity_id}/applications",
        headers=auth(world.student),
        json={"statement": "I have calibrated sensors before in the field."},
    )
    client.post(
        "/api/v1/me/saved", headers=auth(world.student), json={"project_id": world.project_id}
    )

    section = _dashboard(client, world.student)["student"]
    assert isinstance(section, dict)
    assert section["applications_by_status"]["submitted"] == 1
    assert section["applications_by_status"]["accepted"] == 0
    assert section["saved_count"] == 1
    deadlines = section["upcoming_deadlines"]
    assert [d["title"] for d in deadlines] == ["Field assistant for soil sensors"]
    assert deadlines[0]["applied"] is True
    # A sparse profile still gets suggestions (cold start), never an error.
    assert isinstance(section["recommended_opportunities"], list)


def test_student_deadlines_include_saved_openings(client: TestClient, world: World) -> None:
    client.post(
        "/api/v1/me/saved",
        headers=auth(world.student),
        json={"opportunity_id": world.opportunity_id},
    )
    section = _dashboard(client, world.student)["student"]
    assert isinstance(section, dict)
    assert section["upcoming_deadlines"][0]["applied"] is False


def test_faculty_dashboard_counts_only_their_own_work(client: TestClient, world: World) -> None:
    client.post(
        f"/api/v1/opportunities/{world.opportunity_id}/applications",
        headers=auth(world.student),
        json={"statement": "I would like to help with the field trials."},
    )
    client.post(
        "/api/v1/publications",
        headers=auth(world.faculty),
        json={
            "title": "Soil moisture sensing at scale",
            "year": 2025,
            "pub_type": "journal_article",
            "authors": [{"user_id": str(world.faculty.id)}],
        },
    )

    section = _dashboard(client, world.faculty)["faculty"]
    assert isinstance(section, dict)
    assert [p["title"] for p in section["my_projects"]] == ["Low-cost soil sensors"]
    assert section["projects_by_status"]["active"] == 1
    assert [o["title"] for o in section["open_opportunities"]] == [
        "Field assistant for soil sensors"
    ]
    assert section["pending_applications"] == 1
    assert section["publications"] == 1

    # The other faculty member's numbers are their own.
    other = _dashboard(client, world.other_faculty)["faculty"]
    assert isinstance(other, dict)
    assert other["pending_applications"] == 0
    assert other["publications"] == 0
    assert other["projects_by_status"]["draft"] == 1


def test_coordinator_dashboard_shows_their_queues(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    pending_faculty = seed_user(UserRole.FACULTY, department_id=world.department_id)
    client.put(
        "/api/v1/me/profile",
        headers=auth(pending_faculty),
        json={"designation": "Assistant Professor"},
    )
    submitted = client.post(
        "/api/v1/projects",
        headers=auth(world.faculty),
        json={"title": "Second project", "summary": "S", "description": "D"},
    ).json()["id"]
    client.post(f"/api/v1/projects/{submitted}/submit", headers=auth(world.faculty))
    client.post(
        "/api/v1/reports",
        headers=auth(world.student),
        json={
            "target_type": "project",
            "target_id": world.project_id,
            "reason": "The description of this project looks wrong.",
        },
    )

    section = _dashboard(client, world.coordinator)["coordinator"]
    assert isinstance(section, dict)
    assert [item["user_id"] for item in section["pending_verifications"]] == [
        str(pending_faculty.id)
    ]
    assert [p["title"] for p in section["pending_reviews"]] == ["Second project"]
    assert section["open_reports"] == 1
    assert section["department_activity"]["new_projects"] >= 2
    assert section["department_activity"]["new_opportunities"] == 1


def test_admin_dashboard_summarises_the_platform(client: TestClient, world: World) -> None:
    section = _dashboard(client, world.admin)["admin"]
    assert isinstance(section, dict)
    assert section["users_by_role"]["faculty"] == 2
    assert section["users_by_role"]["student"] == 2
    assert section["platform_counts"]["departments"] == 1
    assert section["platform_counts"]["projects"] == 2
    assert section["platform_counts"]["opportunities"] == 1
    assert section["open_reports"] == 0
    # Verification decisions from the fixture are already audited.
    assert len(section["recent_audit"]) > 0
