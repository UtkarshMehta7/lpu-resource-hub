"""Recommendation filters, leakage and cold start against the real API."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.main import create_app
from app.ml.tfidf import INDEX_CACHE
from app.modules.users.models import CoordinatorScopeType, UserRole
from tests.conftest import SeededUser

pytestmark = pytest.mark.db

TOMORROW = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    # The TF-IDF index is cached per process; each test starts from scratch.
    INDEX_CACHE.clear()
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


def _auth(user: SeededUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.access_token}"}


@dataclass
class World:
    admin: SeededUser
    coordinator: SeededUser
    owner: SeededUser
    other_faculty: SeededUser
    student: SeededUser
    fresh_student: SeededUser
    department_id: str
    project_id: str
    skills: dict[str, str] = field(default_factory=dict)
    areas: dict[str, str] = field(default_factory=dict)


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    admin = seed_user(UserRole.ADMIN)
    school_id = client.post(
        "/api/v1/admin/schools", headers=_auth(admin), json={"name": "Engineering School"}
    ).json()["id"]
    department_id = client.post(
        "/api/v1/admin/departments",
        headers=_auth(admin),
        json={"school_id": school_id, "name": "Agriculture"},
    ).json()["id"]
    coordinator = seed_user(
        UserRole.RESEARCH_COORDINATOR,
        department_id=department_id,
        coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
        coordinator_scope_id=department_id,
    )

    skills = {
        name: client.post(
            "/api/v1/taxonomy/skills", headers=_auth(coordinator), json={"name": name}
        ).json()["id"]
        for name in ("Python", "Sensors", "Field Work", "Chromatography")
    }
    parent = client.post(
        "/api/v1/taxonomy/research-areas",
        headers=_auth(coordinator),
        json={"name": "Agricultural Science"},
    ).json()["id"]
    areas = {"Agricultural Science": parent}
    for name in ("Soil Science", "Precision Farming"):
        areas[name] = client.post(
            "/api/v1/taxonomy/research-areas",
            headers=_auth(coordinator),
            json={"name": name, "parent_id": parent},
        ).json()["id"]

    def verified_faculty(bio: str) -> SeededUser:
        faculty = seed_user(UserRole.FACULTY, department_id=department_id)
        client.put(
            "/api/v1/me/profile",
            headers=_auth(faculty),
            json={"designation": "Professor", "bio": bio},
        )
        client.post(
            f"/api/v1/researchers/{faculty.id}/verify",
            headers=_auth(admin),
            json={"decision": "verified"},
        )
        client.put(
            "/api/v1/me/skills",
            headers=_auth(faculty),
            json=[{"skill_id": skills["Sensors"], "proficiency": 5}],
        )
        client.put(
            "/api/v1/me/research-areas",
            headers=_auth(faculty),
            json=[{"research_area_id": areas["Soil Science"], "is_expertise": True}],
        )
        return faculty

    owner = verified_faculty("Soil moisture sensors for smallholder farms.")
    other_faculty = verified_faculty("Analytical chemistry of fertilisers.")

    student = seed_user(UserRole.STUDENT, department_id=department_id)
    client.put(
        "/api/v1/me/profile",
        headers=_auth(student),
        json={
            "program": "B.Tech",
            "year": 3,
            "is_discoverable": True,
            "interests": "soil moisture sensors and field trials on farms",
        },
    )
    client.put(
        "/api/v1/me/skills",
        headers=_auth(student),
        json=[
            {"skill_id": skills["Python"], "proficiency": 4},
            {"skill_id": skills["Sensors"], "proficiency": 5},
            {"skill_id": skills["Field Work"], "proficiency": 3},
        ],
    )
    client.put(
        "/api/v1/me/research-areas",
        headers=_auth(student),
        json=[
            {"research_area_id": areas["Agricultural Science"]},
            {"research_area_id": areas["Soil Science"]},
            {"research_area_id": areas["Precision Farming"]},
        ],
    )

    project_id = client.post(
        "/api/v1/projects",
        headers=_auth(owner),
        json={
            "title": "Low-cost soil sensors",
            "summary": "Cheap sensors for farms.",
            "description": "We build and field-test low-cost soil moisture sensors.",
            "skill_ids": [skills["Sensors"], skills["Field Work"]],
            "research_area_ids": [areas["Soil Science"]],
        },
    ).json()["id"]
    client.post(f"/api/v1/projects/{project_id}/submit", headers=_auth(owner))
    client.post(
        f"/api/v1/projects/{project_id}/review",
        headers=_auth(coordinator),
        json={"decision": "approve"},
    )

    return World(
        admin=admin,
        coordinator=coordinator,
        owner=owner,
        other_faculty=other_faculty,
        student=student,
        fresh_student=seed_user(UserRole.STUDENT, department_id=department_id),
        department_id=department_id,
        project_id=project_id,
        skills=skills,
        areas=areas,
    )


def _opportunity(
    client: TestClient, world: World, *, publish: bool = True, **overrides: object
) -> str:
    body: dict[str, object] = {
        "title": "Field assistant for soil sensors",
        "description": "Help calibrate soil moisture sensors during field trials.",
        "opportunity_type": "research_assistant",
        "project_id": world.project_id,
        "positions": 2,
        "deadline": TOMORROW,
        "skills": [
            {"skill_id": world.skills["Sensors"], "is_required": True},
            {"skill_id": world.skills["Python"], "is_required": False},
        ],
        **overrides,
    }
    response = client.post("/api/v1/opportunities", headers=_auth(world.owner), json=body)
    assert response.status_code == 201, response.text
    opportunity_id: str = response.json()["id"]
    if publish:
        client.post(f"/api/v1/opportunities/{opportunity_id}/publish", headers=_auth(world.owner))
    return opportunity_id


def _recommend(
    client: TestClient, user: SeededUser, target: str, limit: int = 10
) -> dict[str, object]:
    response = client.get(
        "/api/v1/recommendations",
        headers=_auth(user),
        params={"type": target, "limit": limit},
    )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def _ids(body: dict[str, object]) -> list[str]:
    items = body["items"]
    assert isinstance(items, list)
    return [item["item_id"] for item in items]


def test_opportunities_are_ranked_with_real_reasons(client: TestClient, world: World) -> None:
    best = _opportunity(client, world)
    weaker = _opportunity(
        client,
        world,
        title="Lab assistant for chemistry",
        description="Run chromatography on fertiliser samples in the lab.",
        skills=[{"skill_id": world.skills["Python"], "is_required": True}],
    )

    body = _recommend(client, world.student, "opportunities")
    assert body["cold_start"] is False
    assert _ids(body)[:2] == [best, weaker]

    items = body["items"]
    assert isinstance(items, list)
    top = items[0]
    assert top["score"] > items[1]["score"]
    assert top["item"]["title"] == "Field assistant for soil sensors"
    assert any("required skill" in reason for reason in top["reasons"])
    # Nothing is claimed that didn't match: the student has no Chromatography.
    assert not any("Chromatography" in reason for reason in top["reasons"])


def test_business_filters_are_applied_before_scoring(client: TestClient, world: World) -> None:
    visible = _opportunity(client, world)
    draft = _opportunity(client, world, publish=False, title="Unpublished opening")
    applied = _opportunity(client, world, title="Already applied opening")
    client.post(
        f"/api/v1/opportunities/{applied}/applications",
        headers=_auth(world.student),
        json={"statement": "I would like to help with the field trials."},
    )
    collaboration = _opportunity(
        client, world, title="Faculty collaboration", opportunity_type="collaboration"
    )
    closed = _opportunity(client, world, title="Closed opening")
    client.post(f"/api/v1/opportunities/{closed}/close", headers=_auth(world.owner))

    recommended = _ids(_recommend(client, world.student, "opportunities"))
    assert visible in recommended
    for excluded in (draft, applied, collaboration, closed):
        assert excluded not in recommended

    # The poster never gets their own openings back, and faculty only see
    # collaborations.
    assert visible not in _ids(_recommend(client, world.owner, "opportunities"))
    assert _ids(_recommend(client, world.other_faculty, "opportunities")) == [collaboration]


def test_past_deadline_openings_are_dropped(
    client: TestClient, world: World, db_settings: Settings
) -> None:
    stale = _opportunity(client, world, title="Yesterday's opening")
    # Deadlines are compared against the UTC date in the service, so the test
    # must use a UTC date too -- CURRENT_DATE follows the server's timezone
    # and can be a day ahead of UTC.
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    engine = create_engine(str(db_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE opportunities SET deadline = :deadline WHERE id = :id"),
                {"deadline": yesterday, "id": stale},
            )
    finally:
        engine.dispose()
    assert stale not in _ids(_recommend(client, world.student, "opportunities"))


def test_hidden_projects_are_never_recommended(client: TestClient, world: World) -> None:
    hidden = client.post(
        "/api/v1/projects",
        headers=_auth(world.other_faculty),
        json={
            "title": "Secret soil sensor project",
            "summary": "Draft about soil moisture sensors.",
            "description": "Draft work on soil moisture sensors and field trials.",
            "skill_ids": [world.skills["Sensors"]],
            "research_area_ids": [world.areas["Soil Science"]],
        },
    ).json()["id"]

    recommended = _ids(_recommend(client, world.student, "projects"))
    assert world.project_id in recommended
    assert hidden not in recommended
    # The owner doesn't get their own project recommended back to them.
    assert world.project_id not in _ids(_recommend(client, world.owner, "projects"))


def test_researcher_and_collaborator_filters(client: TestClient, world: World) -> None:
    researchers = _ids(_recommend(client, world.student, "researchers"))
    assert str(world.owner.id) in researchers
    assert str(world.student.id) not in researchers  # never yourself
    assert str(world.admin.id) not in researchers

    collaborators = _ids(_recommend(client, world.student, "collaborators"))
    assert str(world.owner.id) in collaborators

    # Once a request is pending, that person stops being suggested.
    client.post(
        "/api/v1/collaborations",
        headers=_auth(world.student),
        json={"recipient_id": str(world.owner.id), "message": "Could I join the field trials?"},
    )
    assert str(world.owner.id) not in _ids(_recommend(client, world.student, "collaborators"))
    # Admins can't send collaboration requests, so they get nothing.
    assert _ids(_recommend(client, world.admin, "collaborators")) == []


def test_private_students_are_not_recommended_as_collaborators(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    private = seed_user(UserRole.STUDENT, department_id=world.department_id)
    client.put(
        "/api/v1/me/profile",
        headers=_auth(private),
        json={"program": "B.Tech", "year": 2, "is_discoverable": False},
    )
    client.put(
        "/api/v1/me/skills",
        headers=_auth(private),
        json=[{"skill_id": world.skills["Sensors"], "proficiency": 5}],
    )
    assert str(private.id) not in _ids(_recommend(client, world.owner, "collaborators"))


def test_cold_start_returns_newest_items_and_says_so(client: TestClient, world: World) -> None:
    _opportunity(client, world)
    newest = _opportunity(client, world, title="Newest opening")

    body = _recommend(client, world.fresh_student, "opportunities", limit=1)
    assert body["cold_start"] is True
    assert _ids(body) == [newest]
    items = body["items"]
    assert isinstance(items, list)
    assert "profile is still incomplete" in items[0]["reasons"][0]


def test_new_content_is_picked_up_without_a_restart(client: TestClient, world: World) -> None:
    """The TF-IDF index is cached, so a fresh opening must still appear."""
    first = _opportunity(client, world)
    assert _ids(_recommend(client, world.student, "opportunities")) == [first]
    second = _opportunity(client, world, title="Second sensor opening")
    assert set(_ids(_recommend(client, world.student, "opportunities"))) == {first, second}
