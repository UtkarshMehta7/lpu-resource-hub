"""Taxonomy integration tests against a real PostgreSQL database."""

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


def _create_skill(client: TestClient, coordinator: SeededUser, name: str) -> str:
    response = client.post(
        "/api/v1/taxonomy/skills", headers=_auth_headers(coordinator), json={"name": name}
    )
    skill_id: str = response.json()["id"]
    return skill_id


def test_create_skill_requires_coordinator_or_admin(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    student = seed_user(UserRole.STUDENT)

    response = client.post(
        "/api/v1/taxonomy/skills", headers=_auth_headers(student), json={"name": "Python"}
    )

    assert response.status_code == 403


def test_coordinator_can_create_skill(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)

    response = client.post(
        "/api/v1/taxonomy/skills", headers=_auth_headers(coordinator), json={"name": "Python"}
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Python"


def test_search_skills_matches_partial_name(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)
    student = seed_user(UserRole.STUDENT)
    _create_skill(client, coordinator, "Machine Learning")
    _create_skill(client, coordinator, "Python")

    response = client.get("/api/v1/skills", params={"q": "machine"}, headers=_auth_headers(student))

    assert response.status_code == 200
    names = [s["name"] for s in response.json()]
    assert names == ["Machine Learning"]


def test_search_skills_resolves_an_alias(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)
    student = seed_user(UserRole.STUDENT)
    skill_id = _create_skill(client, coordinator, "Machine Learning")
    client.post(
        "/api/v1/taxonomy/aliases",
        headers=_auth_headers(coordinator),
        json={"alias": "ML", "skill_id": skill_id},
    )

    response = client.get("/api/v1/skills", params={"q": "ML"}, headers=_auth_headers(student))

    assert response.status_code == 200
    names = [s["name"] for s in response.json()]
    assert "Machine Learning" in names


def test_tag_alias_requires_exactly_one_target(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)

    response = client.post(
        "/api/v1/taxonomy/aliases", headers=_auth_headers(coordinator), json={"alias": "X"}
    )

    assert response.status_code == 422


def test_research_area_rejects_three_levels_deep(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)
    top = client.post(
        "/api/v1/taxonomy/research-areas",
        headers=_auth_headers(coordinator),
        json={"name": "Computer Science"},
    ).json()
    child = client.post(
        "/api/v1/taxonomy/research-areas",
        headers=_auth_headers(coordinator),
        json={"name": "Artificial Intelligence", "parent_id": top["id"]},
    ).json()

    response = client.post(
        "/api/v1/taxonomy/research-areas",
        headers=_auth_headers(coordinator),
        json={"name": "Deep Learning", "parent_id": child["id"]},
    )

    assert response.status_code == 422


def test_tag_suggestion_flow_approve_creates_a_real_skill(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    student = seed_user(UserRole.STUDENT)
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)

    suggestion = client.post(
        "/api/v1/tags/suggestions",
        headers=_auth_headers(student),
        json={"suggested_name": "Rust", "suggested_type": "skill"},
    ).json()
    assert suggestion["status"] == "pending"

    approve_response = client.post(
        f"/api/v1/admin/tag-suggestions/{suggestion['id']}/approve",
        headers=_auth_headers(coordinator),
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    search_response = client.get(
        "/api/v1/skills", params={"q": "Rust"}, headers=_auth_headers(student)
    )
    assert any(s["name"] == "Rust" for s in search_response.json())


def test_tag_suggestion_review_requires_coordinator_or_admin(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    student = seed_user(UserRole.STUDENT)
    faculty = seed_user(UserRole.FACULTY)

    suggestion = client.post(
        "/api/v1/tags/suggestions",
        headers=_auth_headers(student),
        json={"suggested_name": "Go", "suggested_type": "skill"},
    ).json()

    response = client.get("/api/v1/admin/tag-suggestions", headers=_auth_headers(faculty))
    assert response.status_code == 403

    approve_response = client.post(
        f"/api/v1/admin/tag-suggestions/{suggestion['id']}/approve",
        headers=_auth_headers(faculty),
    )
    assert approve_response.status_code == 403


def test_reject_suggestion_does_not_create_anything(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    student = seed_user(UserRole.STUDENT)
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)
    suggestion = client.post(
        "/api/v1/tags/suggestions",
        headers=_auth_headers(student),
        json={"suggested_name": "Cobol", "suggested_type": "skill"},
    ).json()

    reject_response = client.post(
        f"/api/v1/admin/tag-suggestions/{suggestion['id']}/reject",
        headers=_auth_headers(coordinator),
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"

    search_response = client.get(
        "/api/v1/skills", params={"q": "Cobol"}, headers=_auth_headers(student)
    )
    assert search_response.json() == []


def test_approving_an_already_reviewed_suggestion_is_rejected(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    student = seed_user(UserRole.STUDENT)
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)
    suggestion = client.post(
        "/api/v1/tags/suggestions",
        headers=_auth_headers(student),
        json={"suggested_name": "Haskell", "suggested_type": "skill"},
    ).json()
    client.post(
        f"/api/v1/admin/tag-suggestions/{suggestion['id']}/reject",
        headers=_auth_headers(coordinator),
    )

    response = client.post(
        f"/api/v1/admin/tag-suggestions/{suggestion['id']}/approve",
        headers=_auth_headers(coordinator),
    )

    assert response.status_code == 409
