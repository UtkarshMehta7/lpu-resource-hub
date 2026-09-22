"""Opportunity + application workflow, visibility and authorization (real PostgreSQL)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.main import create_app
from app.modules.opportunities import service as opportunity_service
from app.modules.users.models import CoordinatorScopeType, UserRole
from tests.conftest import SeededUser

pytestmark = pytest.mark.db

TOMORROW = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()


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
    coordinator_a: SeededUser
    coordinator_b: SeededUser
    owner: SeededUser
    other_faculty: SeededUser
    student: SeededUser
    student_2: SeededUser
    project_id: str


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

    def verified_faculty() -> SeededUser:
        faculty = seed_user(UserRole.FACULTY, department_id=dept_a)
        client.put("/api/v1/me/profile", headers=_auth(faculty), json={"designation": "Professor"})
        client.post(
            f"/api/v1/researchers/{faculty.id}/verify",
            headers=_auth(admin),
            json={"decision": "verified"},
        )
        return faculty

    coordinator_a = coordinator(dept_a)
    owner = verified_faculty()
    project_id = client.post(
        "/api/v1/projects",
        headers=_auth(owner),
        json={"title": "Soil sensors", "summary": "S", "description": "D"},
    ).json()["id"]
    client.post(f"/api/v1/projects/{project_id}/submit", headers=_auth(owner))
    approved = client.post(
        f"/api/v1/projects/{project_id}/review",
        headers=_auth(coordinator_a),
        json={"decision": "approve"},
    )
    assert approved.json()["status"] == "active", approved.text
    return World(
        admin=admin,
        dept_a=dept_a,
        coordinator_a=coordinator_a,
        coordinator_b=coordinator(dept_b),
        owner=owner,
        other_faculty=verified_faculty(),
        student=seed_user(UserRole.STUDENT, department_id=dept_a),
        student_2=seed_user(UserRole.STUDENT, department_id=dept_a),
        project_id=project_id,
    )


def _body(world: World, **overrides: object) -> dict[str, object]:
    return {
        "title": "Research assistant for soil sensors",
        "description": "Help calibrate soil moisture sensors in the field.",
        "opportunity_type": "research_assistant",
        "project_id": world.project_id,
        "positions": 1,
        "deadline": TOMORROW,
        **overrides,
    }


def _opportunity(
    client: TestClient, world: World, *, publish: bool = True, **overrides: object
) -> str:
    response = client.post(
        "/api/v1/opportunities", headers=_auth(world.owner), json=_body(world, **overrides)
    )
    assert response.status_code == 201, response.text
    opportunity_id: str = response.json()["id"]
    if publish:
        published = client.post(
            f"/api/v1/opportunities/{opportunity_id}/publish", headers=_auth(world.owner)
        )
        assert published.status_code == 200, published.text
    return opportunity_id


def _apply(client: TestClient, user: SeededUser, opportunity_id: str) -> str:
    response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/applications",
        headers=_auth(user),
        json={"statement": "I have calibrated sensors before."},
    )
    assert response.status_code == 201, response.text
    application_id: str = response.json()["id"]
    return application_id


def _set_status(
    client: TestClient, user: SeededUser, application_id: str, status: str, **extra: object
) -> int:
    return client.post(
        f"/api/v1/applications/{application_id}/status",
        headers=_auth(user),
        json={"status": status, **extra},
    ).status_code


# --- opportunities -----------------------------------------------------------


def test_draft_is_private_until_published(client: TestClient, world: World) -> None:
    opportunity_id = _opportunity(client, world, publish=False)
    url = f"/api/v1/opportunities/{opportunity_id}"
    assert client.get(url, headers=_auth(world.student)).status_code == 404
    assert client.get(url, headers=_auth(world.coordinator_a)).status_code == 200
    assert client.get(url, headers=_auth(world.coordinator_b)).status_code == 404
    client.post(f"{url}/publish", headers=_auth(world.owner))
    body = client.get(url, headers=_auth(world.student)).json()
    assert body["status"] == "open"
    assert body["project_title"] == "Soil sensors"
    assert body["department_id"] == world.dept_a


def test_faculty_needs_own_active_project(client: TestClient, world: World) -> None:
    def post(user: SeededUser, **overrides: object) -> int:
        return client.post(
            "/api/v1/opportunities", headers=_auth(user), json=_body(world, **overrides)
        ).status_code

    assert post(world.owner, project_id=None) == 422
    assert post(world.other_faculty) == 403  # not their project
    draft_project = client.post(
        "/api/v1/projects",
        headers=_auth(world.owner),
        json={"title": "Draft", "summary": "S", "description": "D"},
    ).json()["id"]
    assert post(world.owner, project_id=draft_project) == 409
    assert post(world.student) == 403
    assert post(world.owner, deadline="2000-01-01") == 422
    assert post(world.owner, positions=0) == 422


def test_coordinator_creates_department_wide_opening(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/opportunities",
        headers=_auth(world.coordinator_a),
        json=_body(world, project_id=None, opportunity_type="research_internship"),
    )
    assert response.status_code == 201
    assert response.json()["department_id"] == world.dept_a
    # ...and may post on a project in their department.
    on_project = client.post(
        "/api/v1/opportunities", headers=_auth(world.coordinator_a), json=_body(world)
    )
    assert on_project.status_code == 201
    out_of_scope = client.post(
        "/api/v1/opportunities", headers=_auth(world.coordinator_b), json=_body(world)
    )
    assert out_of_scope.status_code == 403


def test_only_owner_edits_and_close_rules(client: TestClient, world: World) -> None:
    opportunity_id = _opportunity(client, world)
    url = f"/api/v1/opportunities/{opportunity_id}"
    assert (
        client.patch(url, headers=_auth(world.other_faculty), json={"title": "X"})
    ).status_code == 403
    assert (client.patch(url, headers=_auth(world.owner), json={"title": "Renamed"})).json()[
        "title"
    ] == "Renamed"
    assert client.post(f"{url}/close", headers=_auth(world.student)).status_code == 403
    assert client.post(f"{url}/close", headers=_auth(world.coordinator_b)).status_code == 403
    assert client.post(f"{url}/close", headers=_auth(world.coordinator_a)).status_code == 200
    assert client.post(f"{url}/close", headers=_auth(world.owner)).status_code == 409
    assert (
        client.patch(url, headers=_auth(world.owner), json={"title": "Again"})
    ).status_code == 409
    logs = client.get("/api/v1/admin/audit-logs", headers=_auth(world.admin)).json()["items"]
    assert any(log["action"] == "opportunity.closed" for log in logs)


def test_filters_and_search(client: TestClient, world: World) -> None:
    _opportunity(client, world)
    _opportunity(
        client,
        world,
        title="Collaborate on spectroscopy",
        description="Joint work.",
        opportunity_type="collaboration",
    )
    _opportunity(client, world, publish=False, title="Hidden draft")

    def titles(user: SeededUser, **params: object) -> list[str]:
        response = client.get("/api/v1/opportunities", headers=_auth(user), params=params)
        return sorted(o["title"] for o in response.json()["items"])

    assert titles(world.student, type="collaboration") == ["Collaborate on spectroscopy"]
    assert "Hidden draft" not in titles(world.student)
    assert "Hidden draft" in titles(world.owner, mine=True)
    assert titles(world.student, deadline_before="2000-01-01") == []
    assert len(titles(world.student, status="open", department_id=world.dept_a)) == 2
    found = client.get(
        "/api/v1/search", headers=_auth(world.student), params={"q": "spectroscopy"}
    ).json()
    assert [o["title"] for o in found["opportunities"]] == ["Collaborate on spectroscopy"]


# --- applying ----------------------------------------------------------------


def test_apply_rules(client: TestClient, world: World) -> None:
    student_opening = _opportunity(client, world)
    collaboration = _opportunity(client, world, opportunity_type="collaboration")

    application = client.post(
        f"/api/v1/opportunities/{student_opening}/applications",
        headers=_auth(world.student),
        json={"statement": "Keen to help."},
    ).json()
    assert application["status"] == "submitted"
    assert [e["status"] for e in application["events"]] == ["submitted"]

    def apply_status(user: SeededUser, opportunity_id: str) -> int:
        return client.post(
            f"/api/v1/opportunities/{opportunity_id}/applications",
            headers=_auth(user),
            json={"statement": "Again"},
        ).status_code

    assert apply_status(world.student, student_opening) == 409  # twice
    assert apply_status(world.other_faculty, student_opening) == 403  # faculty: collab only
    assert apply_status(world.student, collaboration) == 403  # students: not collab
    assert apply_status(world.owner, collaboration) == 403  # own opportunity
    assert apply_status(world.admin, student_opening) == 403  # no permission
    assert apply_status(world.other_faculty, collaboration) == 201


def test_cannot_apply_to_draft_closed_or_after_deadline(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft = _opportunity(client, world, publish=False)
    closed = _opportunity(client, world)
    client.post(f"/api/v1/opportunities/{closed}/close", headers=_auth(world.owner))
    late = _opportunity(client, world)

    def status_for(opportunity_id: str) -> int:
        return client.post(
            f"/api/v1/opportunities/{opportunity_id}/applications",
            headers=_auth(world.student),
            json={"statement": "Hi"},
        ).status_code

    assert status_for(draft) == 404
    assert status_for(closed) == 409
    monkeypatch.setattr(opportunity_service, "today", lambda: date(2999, 1, 1))
    assert status_for(late) == 409


def test_double_apply_blocked_by_unique_constraint(
    client: TestClient, world: World, db_settings: Settings
) -> None:
    opportunity_id = _opportunity(client, world)
    _apply(client, world.student, opportunity_id)
    engine = create_engine(str(db_settings.database_url))
    try:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO applications (opportunity_id, applicant_id, statement) "
                    "VALUES (:o, :a, 'race')"
                ),
                {"o": opportunity_id, "a": str(world.student.id)},
            )
    finally:
        engine.dispose()


# --- deciding ----------------------------------------------------------------


def test_who_can_read_and_decide(client: TestClient, world: World) -> None:
    opportunity_id = _opportunity(client, world)
    application_id = _apply(client, world.student, opportunity_id)
    list_url = f"/api/v1/opportunities/{opportunity_id}/applications"
    detail_url = f"/api/v1/applications/{application_id}"

    assert client.get(list_url, headers=_auth(world.owner)).status_code == 200
    assert client.get(list_url, headers=_auth(world.coordinator_a)).status_code == 200
    assert client.get(list_url, headers=_auth(world.admin)).status_code == 200
    assert client.get(list_url, headers=_auth(world.other_faculty)).status_code == 403
    assert client.get(list_url, headers=_auth(world.coordinator_b)).status_code == 403
    assert client.get(list_url, headers=_auth(world.student)).status_code == 403

    assert client.get(detail_url, headers=_auth(world.student)).status_code == 200
    assert client.get(detail_url, headers=_auth(world.other_faculty)).status_code == 404
    assert client.get(detail_url, headers=_auth(world.student_2)).status_code == 404

    assert _set_status(client, world.student, application_id, "accepted") == 403
    assert _set_status(client, world.coordinator_a, application_id, "under_review") == 403
    assert _set_status(client, world.admin, application_id, "under_review") == 403
    assert _set_status(client, world.other_faculty, application_id, "under_review") == 404


def test_accept_adds_member_fills_and_audits(client: TestClient, world: World) -> None:
    opportunity_id = _opportunity(client, world, positions=1)
    first = _apply(client, world.student, opportunity_id)
    second = _apply(client, world.student_2, opportunity_id)

    assert _set_status(client, world.owner, first, "accepted") == 409  # must review first
    assert _set_status(client, world.owner, first, "under_review") == 200
    assert (
        _set_status(client, world.owner, first, "accepted", add_to_project=True, note="Welcome")
        == 200
    )

    opportunity = client.get(
        f"/api/v1/opportunities/{opportunity_id}", headers=_auth(world.owner)
    ).json()
    assert opportunity["status"] == "filled"
    assert opportunity["accepted_count"] == 1
    members = client.get(
        f"/api/v1/projects/{world.project_id}/members", headers=_auth(world.owner)
    ).json()
    assert [m["user_id"] for m in members] == [str(world.student.id)]

    assert _set_status(client, world.owner, second, "under_review") == 200
    assert _set_status(client, world.owner, second, "accepted") == 409  # no positions left
    assert _set_status(client, world.owner, second, "rejected", note="Filled") == 200

    timeline = client.get("/api/v1/me/applications", headers=_auth(world.student)).json()
    assert [e["status"] for e in timeline[0]["events"]] == [
        "submitted",
        "under_review",
        "accepted",
    ]
    assert timeline[0]["note"] == "Welcome"
    logs = client.get("/api/v1/admin/audit-logs", headers=_auth(world.admin)).json()["items"]
    assert {"application.accepted", "application.rejected"} <= {log["action"] for log in logs}


def test_withdraw_only_by_applicant_before_final_decision(client: TestClient, world: World) -> None:
    opportunity_id = _opportunity(client, world, positions=2)
    mine = _apply(client, world.student, opportunity_id)
    rejected = _apply(client, world.student_2, opportunity_id)

    def withdraw(user: SeededUser, application_id: str) -> int:
        return client.post(
            f"/api/v1/applications/{application_id}/withdraw", headers=_auth(user), json={}
        ).status_code

    assert withdraw(world.owner, mine) == 403
    assert withdraw(world.student, mine) == 200
    assert withdraw(world.student, mine) == 409
    assert _set_status(client, world.owner, mine, "under_review") == 409

    assert _set_status(client, world.owner, rejected, "rejected") == 200
    assert withdraw(world.student_2, rejected) == 409


def test_positions_cannot_drop_below_accepted(client: TestClient, world: World) -> None:
    opportunity_id = _opportunity(client, world, positions=3)
    for student in (world.student, world.student_2):
        application_id = _apply(client, student, opportunity_id)
        _set_status(client, world.owner, application_id, "shortlisted")
        assert _set_status(client, world.owner, application_id, "accepted") == 200

    def patch_positions(positions: int) -> int:
        return client.patch(
            f"/api/v1/opportunities/{opportunity_id}",
            headers=_auth(world.owner),
            json={"positions": positions},
        ).status_code

    assert patch_positions(1) == 422  # two already accepted
    assert patch_positions(2) == 200
