"""Profile integration tests against a real PostgreSQL database."""

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


def _auth_headers(user: SeededUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.access_token}"}


def _create_skills(client: TestClient, coordinator: SeededUser, count: int) -> list[str]:
    ids = []
    for i in range(count):
        response = client.post(
            "/api/v1/taxonomy/skills",
            headers=_auth_headers(coordinator),
            json={"name": f"Skill {i}"},
        )
        ids.append(response.json()["id"])
    return ids


def _create_research_areas(client: TestClient, coordinator: SeededUser, count: int) -> list[str]:
    ids = []
    for i in range(count):
        response = client.post(
            "/api/v1/taxonomy/research-areas",
            headers=_auth_headers(coordinator),
            json={"name": f"Area {i}"},
        )
        ids.append(response.json()["id"])
    return ids


def test_get_profile_404_before_creation(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    student = seed_user(UserRole.STUDENT)

    response = client.get("/api/v1/me/profile", headers=_auth_headers(student))

    assert response.status_code == 404


def test_student_put_profile_creates_student_shape(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    student = seed_user(UserRole.STUDENT)

    response = client.put(
        "/api/v1/me/profile",
        headers=_auth_headers(student),
        json={"program": "B.Tech CSE", "year": 2, "bio": "Hi", "is_discoverable": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile_type"] == "student"
    assert body["program"] == "B.Tech CSE"
    assert body["is_discoverable"] is True


def test_student_default_is_discoverable_is_false(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    student = seed_user(UserRole.STUDENT)

    response = client.put(
        "/api/v1/me/profile",
        headers=_auth_headers(student),
        json={"program": "B.Tech CSE", "year": 1},
    )

    assert response.json()["is_discoverable"] is False


def test_faculty_put_profile_creates_researcher_shape(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    faculty = seed_user(UserRole.FACULTY)

    response = client.put(
        "/api/v1/me/profile",
        headers=_auth_headers(faculty),
        json={
            "designation": "Assistant Professor",
            "bio": "Researcher",
            "availability": "available",
            "links": [{"label": "Homepage", "url": "https://example.com"}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile_type"] == "researcher"
    assert body["verification_status"] == "unverified"
    assert body["links"] == [{"label": "Homepage", "url": "https://example.com"}]


def test_researcher_profile_rejects_a_non_http_link(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    faculty = seed_user(UserRole.FACULTY)

    response = client.put(
        "/api/v1/me/profile",
        headers=_auth_headers(faculty),
        json={
            "designation": "Assistant Professor",
            "links": [{"label": "Bad", "url": "javascript:alert(1)"}],
        },
    )

    assert response.status_code == 422


def test_put_profile_is_idempotent_upsert(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    student = seed_user(UserRole.STUDENT)
    client.put(
        "/api/v1/me/profile",
        headers=_auth_headers(student),
        json={"program": "First", "year": 1},
    )

    response = client.put(
        "/api/v1/me/profile",
        headers=_auth_headers(student),
        json={"program": "Second", "year": 2},
    )

    assert response.status_code == 200
    assert response.json()["program"] == "Second"

    get_response = client.get("/api/v1/me/profile", headers=_auth_headers(student))
    assert get_response.json()["program"] == "Second"


def test_onboarding_complete_flips_at_three_skills_and_three_areas(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)
    student = seed_user(UserRole.STUDENT)
    skill_ids = _create_skills(client, coordinator, 3)
    area_ids = _create_research_areas(client, coordinator, 3)

    # Only 2 of 3 skills, 0 research areas: still incomplete.
    client.put(
        "/api/v1/me/skills",
        headers=_auth_headers(student),
        json=[{"skill_id": sid, "proficiency": 3} for sid in skill_ids[:2]],
    )
    assert (
        client.get("/api/v1/me", headers=_auth_headers(student)).json()["onboarding_complete"]
        is False
    )

    # 3rd skill added, but still 0 research areas: still incomplete.
    client.put(
        "/api/v1/me/skills",
        headers=_auth_headers(student),
        json=[{"skill_id": sid, "proficiency": 3} for sid in skill_ids],
    )
    assert (
        client.get("/api/v1/me", headers=_auth_headers(student)).json()["onboarding_complete"]
        is False
    )

    # 3 skills + 3 research areas: complete.
    client.put(
        "/api/v1/me/research-areas",
        headers=_auth_headers(student),
        json=[{"research_area_id": aid, "is_expertise": False} for aid in area_ids],
    )
    assert (
        client.get("/api/v1/me", headers=_auth_headers(student)).json()["onboarding_complete"]
        is True
    )


def test_put_skills_rejects_unknown_skill_id(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    student = seed_user(UserRole.STUDENT)

    response = client.put(
        "/api/v1/me/skills",
        headers=_auth_headers(student),
        json=[{"skill_id": "11111111-1111-1111-1111-111111111111", "proficiency": 3}],
    )

    assert response.status_code == 404


def test_put_skills_replaces_the_full_set(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)
    student = seed_user(UserRole.STUDENT)
    skill_ids = _create_skills(client, coordinator, 2)

    client.put(
        "/api/v1/me/skills",
        headers=_auth_headers(student),
        json=[{"skill_id": skill_ids[0], "proficiency": 5}],
    )
    response = client.put(
        "/api/v1/me/skills",
        headers=_auth_headers(student),
        json=[{"skill_id": skill_ids[1], "proficiency": 2}],
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["skill_id"] == skill_ids[1]
