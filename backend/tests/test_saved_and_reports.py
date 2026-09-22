"""Saved items and content reports (real PostgreSQL)."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import SeededUser
from tests.world import World, auth, build_world

pytestmark = pytest.mark.db

UNKNOWN_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    return build_world(client, seed_user)


def _save(client: TestClient, user: SeededUser, **target: str) -> tuple[int, dict[str, object]]:
    response = client.post("/api/v1/me/saved", headers=auth(user), json=target)
    body: dict[str, object] = response.json()
    return response.status_code, body


# --- saved items --------------------------------------------------------------


def test_saving_each_kind_of_item(client: TestClient, world: World) -> None:
    for target in (
        {"project_id": world.project_id},
        {"opportunity_id": world.opportunity_id},
        {"researcher_id": str(world.faculty.id)},
    ):
        code, body = _save(client, world.student, **target)
        assert code == 201, body

    saved = client.get("/api/v1/me/saved", headers=auth(world.student)).json()
    assert sorted(entry["saved_type"] for entry in saved) == [
        "opportunity",
        "project",
        "researcher",
    ]
    only_projects = client.get(
        "/api/v1/me/saved", headers=auth(world.student), params={"type": "project"}
    ).json()
    assert [entry["item"]["title"] for entry in only_projects] == ["Low-cost soil sensors"]
    # Saved lists are private.
    assert client.get("/api/v1/me/saved", headers=auth(world.other_student)).json() == []


def test_saving_is_validated_and_deduplicated(client: TestClient, world: World) -> None:
    assert _save(client, world.student, project_id=world.project_id)[0] == 201
    assert _save(client, world.student, project_id=world.project_id)[0] == 409
    # Exactly one target, and only things you can see.
    assert (
        client.post(
            "/api/v1/me/saved",
            headers=auth(world.student),
            json={"project_id": world.project_id, "opportunity_id": world.opportunity_id},
        ).status_code
        == 422
    )
    assert client.post("/api/v1/me/saved", headers=auth(world.student), json={}).status_code == 422
    assert _save(client, world.student, project_id=world.draft_project_id)[0] == 404
    assert _save(client, world.student, project_id=UNKNOWN_ID)[0] == 404


def test_saved_items_never_widen_visibility(client: TestClient, world: World) -> None:
    """A project that stops being visible simply stops appearing."""
    _save(client, world.student, project_id=world.project_id)
    assert len(client.get("/api/v1/me/saved", headers=auth(world.student)).json()) == 1
    client.post(f"/api/v1/projects/{world.project_id}/archive", headers=auth(world.faculty))
    assert client.get("/api/v1/me/saved", headers=auth(world.student)).json() == []


def test_only_the_owner_can_delete_a_saved_item(client: TestClient, world: World) -> None:
    _, body = _save(client, world.student, project_id=world.project_id)
    saved_id = body["id"]
    assert (
        client.delete(f"/api/v1/me/saved/{saved_id}", headers=auth(world.other_student))
    ).status_code == 404
    assert (
        client.delete(f"/api/v1/me/saved/{saved_id}", headers=auth(world.student))
    ).status_code == 204
    assert client.get("/api/v1/me/saved", headers=auth(world.student)).json() == []


# --- reports ------------------------------------------------------------------


def _report(
    client: TestClient, user: SeededUser, target_id: str, **overrides: object
) -> tuple[int, dict[str, object]]:
    response = client.post(
        "/api/v1/reports",
        headers=auth(user),
        json={
            "target_type": "project",
            "target_id": target_id,
            "reason": "This project description looks like spam to me.",
            **overrides,
        },
    )
    body: dict[str, object] = response.json()
    return response.status_code, body


def test_reporting_requires_a_visible_target(client: TestClient, world: World) -> None:
    code, body = _report(client, world.student, world.project_id)
    assert code == 201, body
    assert body["status"] == "open"
    assert body["target_title"] == "Low-cost soil sensors"

    assert _report(client, world.student, world.project_id)[0] == 409  # duplicate
    assert _report(client, world.student, world.draft_project_id)[0] == 404
    assert _report(client, world.student, UNKNOWN_ID)[0] == 404
    assert (
        client.post(
            "/api/v1/reports",
            headers=auth(world.student),
            json={"target_type": "project", "target_id": world.project_id, "reason": "short"},
        ).status_code
        == 422
    )


def test_only_moderators_see_and_resolve_the_queue(client: TestClient, world: World) -> None:
    _, report = _report(client, world.student, world.project_id)
    report_id = report["id"]

    assert client.get("/api/v1/admin/reports", headers=auth(world.student)).status_code == 403
    assert client.get("/api/v1/admin/reports", headers=auth(world.faculty)).status_code == 403
    for moderator in (world.coordinator, world.admin):
        queue = client.get("/api/v1/admin/reports", headers=auth(moderator))
        assert queue.status_code == 200
        assert [item["id"] for item in queue.json()] == [report_id]

    resolve_url = f"/api/v1/admin/reports/{report_id}/resolve"
    assert (
        client.post(
            resolve_url, headers=auth(world.student), json={"status": "dismissed"}
        ).status_code
        == 403
    )
    resolved = client.post(
        resolve_url,
        headers=auth(world.coordinator),
        json={"status": "dismissed", "note": "Looks fine."},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "dismissed"
    assert resolved.json()["reviewed_by"] == str(world.coordinator.id)
    # Resolving twice is a conflict, and the queue is empty again.
    assert (
        client.post(resolve_url, headers=auth(world.admin), json={"status": "actioned"})
    ).status_code == 409
    assert client.get("/api/v1/admin/reports", headers=auth(world.admin)).json() == []
    assert (
        client.get(
            "/api/v1/admin/reports", headers=auth(world.admin), params={"status": "dismissed"}
        ).json()[0]["id"]
        == report_id
    )

    logs = client.get("/api/v1/admin/audit-logs", headers=auth(world.admin)).json()["items"]
    assert any(log["action"] == "report.dismissed" for log in logs)
    # Once resolved, the same person may report it again.
    assert _report(client, world.student, world.project_id)[0] == 201


def test_reports_cannot_set_their_own_status(client: TestClient, world: World) -> None:
    code, body = _report(client, world.student, target_id=world.project_id, status="actioned")
    assert code == 201
    assert body["status"] == "open"
