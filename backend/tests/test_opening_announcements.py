"""A published opening goes on the board (ADR 0041).

The thing worth holding here is not that a notice appears -- it is the three
properties that make raising one automatically safe, given that
`ANNOUNCEMENT_POST` is deliberately withheld from faculty (ADR 0038): the reach
is the OPENING's department rather than the poster's, the content is derived
rather than typed, and one opening can only ever be on the board once.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
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


class Stage:
    def __init__(self, client: TestClient, seed_user: Callable[..., SeededUser]) -> None:
        self.admin = seed_user(UserRole.ADMIN)
        self.dept = _department(client, self.admin, "Agriculture")
        self.other_dept = _department(client, self.admin, "Chemistry")
        self.coordinator = seed_user(
            UserRole.RESEARCH_COORDINATOR,
            department_id=self.dept,
            coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
            coordinator_scope_id=self.dept,
        )
        self.owner = seed_user(UserRole.FACULTY, department_id=self.dept)
        # A project is only approved for a verified researcher, and an opening
        # is only posted on an active project.
        client.put(
            "/api/v1/me/profile", headers=_auth(self.owner), json={"designation": "Professor"}
        )
        client.post(
            f"/api/v1/researchers/{self.owner.id}/verify",
            headers=_auth(self.admin),
            json={"decision": "verified"},
        )
        self.student = seed_user(UserRole.STUDENT, department_id=self.dept)
        self.outsider = seed_user(UserRole.STUDENT, department_id=self.other_dept)

        self.project_id = client.post(
            "/api/v1/projects",
            headers=_auth(self.owner),
            json={"title": "Soil sensors", "summary": "S", "description": "D"},
        ).json()["id"]
        client.post(f"/api/v1/projects/{self.project_id}/submit", headers=_auth(self.owner))
        approved = client.post(
            f"/api/v1/projects/{self.project_id}/review",
            headers=_auth(self.coordinator),
            json={"decision": "approve"},
        )
        assert approved.json()["status"] == "active", approved.text


@pytest.fixture
def stage(client: TestClient, seed_user: Callable[..., SeededUser]) -> Stage:
    return Stage(client, seed_user)


def _opening(client: TestClient, stage: Stage, **overrides: object) -> str:
    response = client.post(
        "/api/v1/opportunities",
        headers=_auth(stage.owner),
        json={
            "title": "Research assistant for soil sensors",
            "description": "Help calibrate soil moisture sensors in the field.",
            "opportunity_type": "research_assistant",
            "project_id": stage.project_id,
            "positions": 1,
            "deadline": TOMORROW,
            **overrides,
        },
    )
    assert response.status_code == 201, response.text
    opportunity_id: str = response.json()["id"]
    return opportunity_id


def _board(client: TestClient, user: SeededUser) -> list[dict[str, object]]:
    response = client.get("/api/v1/announcements", headers=_auth(user))
    assert response.status_code == 200, response.text
    items: list[dict[str, object]] = response.json()["items"]
    return items


def test_a_draft_opening_is_on_nobodys_board(client: TestClient, stage: Stage) -> None:
    """A draft belongs to its author. Announcing one would publish it."""
    _opening(client, stage)

    assert _board(client, stage.student) == []


def test_publishing_an_opening_puts_it_on_the_board(client: TestClient, stage: Stage) -> None:
    opportunity_id = _opening(client, stage)
    assert (
        client.post(
            f"/api/v1/opportunities/{opportunity_id}/publish", headers=_auth(stage.owner)
        ).status_code
        == 200
    )

    notices = _board(client, stage.student)
    assert len(notices) == 1
    assert notices[0]["source_opportunity_id"] == opportunity_id
    assert "Research assistant for soil sensors" in str(notices[0]["subject"])
    # Frozen at post time like any notice, and attributed to the person whose
    # opening it is rather than to "the institution".
    assert notices[0]["posted_by"] == str(stage.owner.id)
    assert notices[0]["posted_by_role"] == "faculty"


def test_the_reach_is_the_openings_department_not_the_posters_rank(
    client: TestClient, stage: Stage
) -> None:
    """The guard that makes this safe at all.

    `ANNOUNCEMENT_POST` is withheld from faculty on purpose, because
    `ROLE_HIERARCHY` would otherwise hand an institution-wide megaphone to
    every faculty member. Publishing an opening must not become that route, so
    the audience comes from the OPENING -- which already belongs to one
    department -- and never from `reach_of`.
    """
    opportunity_id = _opening(client, stage)
    client.post(f"/api/v1/opportunities/{opportunity_id}/publish", headers=_auth(stage.owner))

    notices = _board(client, stage.student)
    assert notices[0]["audience"] == "department"
    assert notices[0]["department_id"] == stage.dept

    # Somebody in another department is not told about it.
    assert _board(client, stage.outsider) == []


def test_a_closed_opening_cannot_be_reopened_so_its_notice_stays_down(
    client: TestClient, stage: Stage
) -> None:
    """There is no CLOSED -> OPEN in `opportunities/policies.py:TRANSITIONS`.

    Worth asserting here rather than only there, because the board's behaviour
    depends on it: an opening is published exactly once in its life, which is
    what makes "one notice per opening" true in practice as well as in the
    UNIQUE constraint.
    """
    opportunity_id = _opening(client, stage)
    client.post(f"/api/v1/opportunities/{opportunity_id}/publish", headers=_auth(stage.owner))
    client.post(f"/api/v1/opportunities/{opportunity_id}/close", headers=_auth(stage.owner))

    reopened = client.post(
        f"/api/v1/opportunities/{opportunity_id}/publish", headers=_auth(stage.owner)
    )
    assert reopened.status_code == 409, reopened.text
    assert _board(client, stage.student) == []


def test_closing_an_opening_takes_its_notice_down(client: TestClient, stage: Stage) -> None:
    """A board advertising a closed opening is worse than one that never
    mentioned it: somebody reads it, goes to apply, and finds a door that does
    not open."""
    opportunity_id = _opening(client, stage)
    client.post(f"/api/v1/opportunities/{opportunity_id}/publish", headers=_auth(stage.owner))
    assert len(_board(client, stage.student)) == 1

    client.post(f"/api/v1/opportunities/{opportunity_id}/close", headers=_auth(stage.owner))

    assert _board(client, stage.student) == []


def test_a_withdrawn_notice_is_taken_down_not_deleted(client: TestClient, stage: Stage) -> None:
    """Said to everybody is not unsayable, but it can stop being said.

    The row stays, which is why an administrator -- the one reader who sees
    withdrawn notices -- can still account for what was announced.
    """
    opportunity_id = _opening(client, stage)
    client.post(f"/api/v1/opportunities/{opportunity_id}/publish", headers=_auth(stage.owner))
    client.post(f"/api/v1/opportunities/{opportunity_id}/close", headers=_auth(stage.owner))

    assert _board(client, stage.student) == []
    seen_by_admin = [
        notice
        for notice in _board(client, stage.admin)
        if notice["source_opportunity_id"] == opportunity_id
    ]
    assert len(seen_by_admin) == 1
    assert seen_by_admin[0]["status"] == "withdrawn"


def test_filling_the_last_place_takes_the_notice_down_too(client: TestClient, stage: Stage) -> None:
    """FILLED and CLOSED mean the same thing to a reader, so both raise the
    one event."""
    opportunity_id = _opening(client, stage, positions=1)
    client.post(f"/api/v1/opportunities/{opportunity_id}/publish", headers=_auth(stage.owner))

    application_id = client.post(
        f"/api/v1/opportunities/{opportunity_id}/applications",
        headers=_auth(stage.student),
        json={"statement": "I have calibrated sensors before."},
    ).json()["id"]
    for target in ("under_review", "accepted"):
        assert (
            client.post(
                f"/api/v1/applications/{application_id}/status",
                headers=_auth(stage.owner),
                json={"status": target},
            ).status_code
            == 200
        )

    assert _board(client, stage.student) == []


def test_a_hand_written_notice_names_no_opening(client: TestClient, stage: Stage) -> None:
    """Postgres allows any number of NULLs in a unique column, which is what
    lets the constraint hold without constraining ordinary notices."""
    created = client.post(
        "/api/v1/announcements",
        headers=_auth(stage.coordinator),
        json={"subject": "Disclosure window closes Friday", "body": "Please file by then."},
    )
    assert created.status_code == 201, created.text
    assert created.json()["source_opportunity_id"] is None

    second = client.post(
        "/api/v1/announcements",
        headers=_auth(stage.coordinator),
        json={"subject": "And again", "body": "Still Friday."},
    )
    assert second.status_code == 201, second.text
