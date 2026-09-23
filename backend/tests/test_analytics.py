"""Analytics, the collaboration network, moderation actions and settings.

The theme of these tests is scope: a coordinator's numbers stop at their
department, an admin's don't, and neither exposes personal data.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.users.models import CoordinatorScopeType, UserRole
from tests.conftest import SeededUser
from tests.world import World, auth, build_world

pytestmark = pytest.mark.db


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    return build_world(client, seed_user)


def _overview(client: TestClient, user: SeededUser) -> dict[str, object]:
    response = client.get("/api/v1/analytics/overview", headers=auth(user))
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_analytics_is_for_coordinators_and_admins_only(client: TestClient, world: World) -> None:
    for user in (world.student, world.faculty):
        assert client.get("/api/v1/analytics/overview", headers=auth(user)).status_code == 403
        assert client.get("/api/v1/analytics/network", headers=auth(user)).status_code == 403
    assert (
        client.get("/api/v1/analytics/overview", headers=auth(world.coordinator)).status_code == 200
    )
    assert client.get("/api/v1/analytics/network", headers=auth(world.admin)).status_code == 200


def test_overview_reports_the_expected_shape(client: TestClient, world: World) -> None:
    client.post(
        f"/api/v1/opportunities/{world.opportunity_id}/applications",
        headers=auth(world.student),
        json={"statement": "I would like to help with the field trials."},
    )

    admin_view = _overview(client, world.admin)
    assert admin_view["scope"] == "platform"
    assert admin_view["projects_by_status"]["active"] == 1
    assert admin_view["projects_by_status"]["draft"] == 1
    assert admin_view["opportunity_funnel"]["opportunities_open"] == 1
    assert admin_view["opportunity_funnel"]["applications_submitted"] == 1
    assert len(admin_view["trends"]) == 6
    assert admin_view["trends"][-1]["projects"] >= 2  # this month's fixture data

    coordinator_view = _overview(client, world.coordinator)
    assert coordinator_view["scope"] == "department"
    assert coordinator_view["department_id"] == world.department_id


def test_a_coordinator_sees_only_their_own_department(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    school_id = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "Science School"}
    ).json()["id"]
    other_department = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": school_id, "name": "Chemistry"},
    ).json()["id"]
    outsider = seed_user(
        UserRole.RESEARCH_COORDINATOR,
        department_id=other_department,
        coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
        coordinator_scope_id=other_department,
    )

    theirs = _overview(client, outsider)
    assert theirs["scope"] == "department"
    # The fixture's projects belong to the other department, so they see none.
    assert sum(theirs["projects_by_status"].values()) == 0
    assert theirs["opportunity_funnel"]["opportunities_open"] == 0

    ours = _overview(client, world.coordinator)
    assert sum(ours["projects_by_status"].values()) == 2


def test_a_coordinator_without_a_scope_sees_nothing(
    client: TestClient, seed_user: Callable[..., SeededUser], world: World
) -> None:
    unscoped = seed_user(UserRole.RESEARCH_COORDINATOR)

    body = _overview(client, unscoped)

    assert sum(body["projects_by_status"].values()) == 0
    assert body["verification_backlog"]["pending"] == 0


def test_network_contains_no_personal_contact_details(client: TestClient, world: World) -> None:
    # Give the graph an edge: the student joins the faculty member's project.
    client.post(
        f"/api/v1/projects/{world.project_id}/members",
        headers=auth(world.faculty),
        json={"user_id": str(world.student.id), "member_role": "research assistant"},
    )

    response = client.get("/api/v1/analytics/network", headers=auth(world.admin))
    assert response.status_code == 200
    graph = response.json()

    assert graph["scope"] == "platform"
    names = {node["full_name"] for node in graph["nodes"]}
    assert any(name for name in names)
    for node in graph["nodes"]:
        assert set(node) == {
            "id",
            "full_name",
            "role",
            "department_id",
            "degree",
            "connected",
        }
        assert "email" not in node
        assert "registration_number" not in node

    edge_pairs = {(edge["source"], edge["target"]) for edge in graph["edges"]}
    pair = (str(world.faculty.id), str(world.student.id))
    assert pair in edge_pairs or tuple(reversed(pair)) in edge_pairs


def test_network_excludes_students_who_did_not_opt_in(client: TestClient, world: World) -> None:
    graph = client.get("/api/v1/analytics/network", headers=auth(world.admin)).json()
    ids = {node["id"] for node in graph["nodes"]}

    assert str(world.student.id) in ids  # discoverable
    assert str(world.other_student.id) not in ids  # opted out


def test_moderation_can_hide_the_reported_content(client: TestClient, world: World) -> None:
    report_id = client.post(
        "/api/v1/reports",
        headers=auth(world.student),
        json={
            "target_type": "project",
            "target_id": world.project_id,
            "reason": "This project description looks like spam to me.",
        },
    ).json()["id"]

    resolved = client.post(
        f"/api/v1/admin/reports/{report_id}/resolve",
        headers=auth(world.coordinator),
        json={"status": "actioned", "note": "Taken down.", "hide_target": True},
    )
    assert resolved.status_code == 200

    project = client.get(f"/api/v1/projects/{world.project_id}", headers=auth(world.faculty)).json()
    assert project["status"] == "archived"

    logs = client.get(
        "/api/v1/admin/audit-logs", headers=auth(world.admin), params={"action": "report.actioned"}
    ).json()["items"]
    assert logs[0]["after"]["hidden"] is True


def test_platform_settings_are_admin_only_and_carry_no_secrets(
    client: TestClient, world: World
) -> None:
    assert client.get("/api/v1/admin/settings", headers=auth(world.coordinator)).status_code == 403

    response = client.get("/api/v1/admin/settings", headers=auth(world.admin))
    assert response.status_code == 200
    body = response.json()
    assert body["environment"]
    assert "recommendation_weights" in body["settings"]
    serialised = str(body).lower()
    for secret in ("password", "secret", "jwt", "database_url"):
        assert secret not in serialised
