"""Milestones through the API: who may plan, who may move, who may not look.

The headline cases are `test_a_member_may_complete_but_not_cancel` -- the split
that the whole permission design turns on -- and
`test_a_cycle_is_refused_however_long_the_chain`, because a dependency graph
that can loop makes the at-risk derivation non-terminating.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.main import create_app
from tests.conftest import SeededUser
from tests.world import World, auth, build_world

pytestmark = pytest.mark.db

TODAY = datetime.now(UTC).date()


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    return build_world(client, seed_user)


def add_milestone(
    client: TestClient, world: World, *, title: str = "Survey", due: int = 30, **extra: object
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/projects/{world.project_id}/milestones",
        headers=auth(world.faculty),
        json={"title": title, "due_date": day(due), **extra},
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def make_member(client: TestClient, world: World) -> SeededUser:
    response = client.post(
        f"/api/v1/projects/{world.project_id}/members",
        headers=auth(world.faculty),
        json={"user_id": str(world.student.id), "member_role": "Research assistant"},
    )
    assert response.status_code in (200, 201), response.text
    return world.student


# --- planning --------------------------------------------------------------


def test_the_owner_plans_milestones_and_they_come_back_in_order(
    client: TestClient, world: World
) -> None:
    add_milestone(client, world, title="Third", due=60)
    add_milestone(client, world, title="First", due=10)
    add_milestone(client, world, title="Second", due=20)

    listed = client.get(
        f"/api/v1/projects/{world.project_id}/milestones", headers=auth(world.faculty)
    ).json()
    # Plan order, which is insertion order here -- not date order.
    assert [m["title"] for m in listed] == ["Third", "First", "Second"]
    assert [m["position"] for m in listed] == [1, 2, 3]


def test_inserting_at_a_position_pushes_the_rest_down(client: TestClient, world: World) -> None:
    add_milestone(client, world, title="A", due=10)
    add_milestone(client, world, title="C", due=30)
    add_milestone(client, world, title="B", due=20, position=2)

    listed = client.get(
        f"/api/v1/projects/{world.project_id}/milestones", headers=auth(world.faculty)
    ).json()
    assert [m["title"] for m in listed] == ["A", "B", "C"]


def test_only_the_owner_may_add_a_milestone(client: TestClient, world: World) -> None:
    member = make_member(client, world)
    response = client.post(
        f"/api/v1/projects/{world.project_id}/milestones",
        headers=auth(member),
        json={"title": "Sneaky", "due_date": day(5)},
    )
    assert response.status_code == 403


def test_a_project_nobody_may_see_hides_its_milestones(client: TestClient, world: World) -> None:
    """A draft belonging to somebody else is a 404, not a 403."""
    response = client.get(
        f"/api/v1/projects/{world.draft_project_id}/milestones", headers=auth(world.student)
    )
    assert response.status_code == 404


def test_a_milestone_of_an_invisible_project_is_a_404(client: TestClient, world: World) -> None:
    created = client.post(
        f"/api/v1/projects/{world.draft_project_id}/milestones",
        headers=auth(world.other_faculty),
        json={"title": "Private", "due_date": day(5)},
    ).json()
    response = client.get(f"/api/v1/milestones/{created['id']}", headers=auth(world.student))
    assert response.status_code == 404


def test_a_deleted_draft_takes_its_milestones_out_of_view(client: TestClient, world: World) -> None:
    """Deleting a draft is a *soft* delete, so the foreign key never fires.

    What makes the milestone disappear is that its project stopped being
    visible -- which is exactly why milestone visibility is composed from the
    project's rule rather than being written out a second time here.
    """
    milestone = client.post(
        f"/api/v1/projects/{world.draft_project_id}/milestones",
        headers=auth(world.other_faculty),
        json={"title": "Doomed", "due_date": day(5)},
    ).json()
    assert (
        client.get(
            f"/api/v1/milestones/{milestone['id']}", headers=auth(world.other_faculty)
        ).status_code
        == 200
    )

    client.delete(f"/api/v1/projects/{world.draft_project_id}", headers=auth(world.other_faculty))
    gone = client.get(f"/api/v1/milestones/{milestone['id']}", headers=auth(world.other_faculty))
    assert gone.status_code == 404


def test_archiving_keeps_the_history(client: TestClient, world: World) -> None:
    """An approved project is archived, not deleted, so its plan survives."""
    milestone = add_milestone(client, world)
    client.delete(f"/api/v1/projects/{world.project_id}", headers=auth(world.admin))
    kept = client.get(f"/api/v1/milestones/{milestone['id']}", headers=auth(world.faculty))
    assert kept.status_code == 200


def test_the_foreign_key_really_cascades(db_settings: Settings, world: World) -> None:
    """Nothing in the app hard-deletes a project, but if anything ever does,
    orphaned milestones must not be left behind."""
    engine = create_engine(str(db_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO milestones (project_id, title, due_date, position) "
                    "VALUES (:pid, 'Orphan check', CURRENT_DATE, 99)"
                ),
                {"pid": world.project_id},
            )
            connection.execute(
                text("DELETE FROM projects WHERE id = :pid"), {"pid": world.project_id}
            )
            left = connection.execute(
                text("SELECT count(*) FROM milestones WHERE project_id = :pid"),
                {"pid": world.project_id},
            ).scalar_one()
        assert left == 0
    finally:
        engine.dispose()


# --- risk on the wire ------------------------------------------------------


def test_the_api_reports_the_derived_risk(client: TestClient, world: World) -> None:
    on_track = add_milestone(client, world, title="Far off", due=60)
    at_risk = add_milestone(client, world, title="Soon", due=2)
    overdue = add_milestone(client, world, title="Late", due=-3)

    assert on_track["risk"] == "on_track"
    assert at_risk["risk"] == "at_risk"
    assert overdue["risk"] == "overdue"
    assert overdue["days_until_due"] == -3


def test_a_blocked_milestone_names_what_is_holding_it_up(client: TestClient, world: World) -> None:
    late = add_milestone(client, world, title="Late dependency", due=-5)
    blocked = add_milestone(client, world, title="Waiting", due=60)

    updated = client.post(
        f"/api/v1/milestones/{blocked['id']}/dependencies",
        headers=auth(world.faculty),
        json={"depends_on_id": late["id"]},
    ).json()

    assert updated["risk"] == "blocked"
    assert [m["title"] for m in updated["blocked_by"]] == ["Late dependency"]
    assert [m["title"] for m in updated["depends_on"]] == ["Late dependency"]


# --- moving it along -------------------------------------------------------


def test_completing_a_milestone_records_who_and_when(client: TestClient, world: World) -> None:
    milestone = add_milestone(client, world)
    done = client.post(
        f"/api/v1/milestones/{milestone['id']}/status",
        headers=auth(world.faculty),
        json={"status": "done"},
    ).json()
    assert done["status"] == "done"
    assert done["completed_at"] is not None
    assert done["completed_by"] == str(world.faculty.id)
    # Settled work is not "on track" -- it is simply no longer outstanding.
    assert done["risk"] == "none"


def test_reopening_clears_the_record_of_completion(client: TestClient, world: World) -> None:
    milestone = add_milestone(client, world)
    client.post(
        f"/api/v1/milestones/{milestone['id']}/status",
        headers=auth(world.faculty),
        json={"status": "done"},
    )
    reopened = client.post(
        f"/api/v1/milestones/{milestone['id']}/status",
        headers=auth(world.faculty),
        json={"status": "in_progress"},
    ).json()
    assert reopened["completed_at"] is None
    assert reopened["completed_by"] is None


def test_a_member_may_complete_but_not_cancel(client: TestClient, world: World) -> None:
    """The split the permission design turns on.

    Moving work along is the team's motion and happens weekly; striking work
    off the plan is the owner's and happens rarely.
    """
    member = make_member(client, world)
    milestone = add_milestone(client, world)

    completed = client.post(
        f"/api/v1/milestones/{milestone['id']}/status",
        headers=auth(member),
        json={"status": "done"},
    )
    assert completed.status_code == 200
    assert completed.json()["completed_by"] == str(member.id)

    second = add_milestone(client, world, title="Another")
    cancelled = client.post(
        f"/api/v1/milestones/{second['id']}/status",
        headers=auth(member),
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 409


def test_a_bystander_may_read_but_never_move(client: TestClient, world: World) -> None:
    """The project is active, so it is public -- readable, not writable."""
    milestone = add_milestone(client, world)
    assert (
        client.get(f"/api/v1/milestones/{milestone['id']}", headers=auth(world.student)).status_code
        == 200
    )
    response = client.post(
        f"/api/v1/milestones/{milestone['id']}/status",
        headers=auth(world.student),
        json={"status": "done"},
    )
    assert response.status_code == 403


def test_a_move_that_is_not_in_the_table_is_refused(client: TestClient, world: World) -> None:
    milestone = add_milestone(client, world)
    client.post(
        f"/api/v1/milestones/{milestone['id']}/status",
        headers=auth(world.faculty),
        json={"status": "cancelled"},
    )
    # cancelled -> done is not a transition anyone may make.
    response = client.post(
        f"/api/v1/milestones/{milestone['id']}/status",
        headers=auth(world.faculty),
        json={"status": "done"},
    )
    assert response.status_code == 409


# --- dependencies ----------------------------------------------------------


def test_a_milestone_cannot_wait_on_itself(client: TestClient, world: World) -> None:
    milestone = add_milestone(client, world)
    response = client.post(
        f"/api/v1/milestones/{milestone['id']}/dependencies",
        headers=auth(world.faculty),
        json={"depends_on_id": milestone["id"]},
    )
    assert response.status_code == 409


def test_a_cycle_is_refused_however_long_the_chain(client: TestClient, world: World) -> None:
    """A -> B -> C, then C -> A would loop, and the risk walk would not end."""
    a = add_milestone(client, world, title="A", due=10)
    b = add_milestone(client, world, title="B", due=20)
    c = add_milestone(client, world, title="C", due=30)

    for downstream, upstream in ((b, a), (c, b)):
        assert (
            client.post(
                f"/api/v1/milestones/{downstream['id']}/dependencies",
                headers=auth(world.faculty),
                json={"depends_on_id": upstream["id"]},
            ).status_code
            == 200
        )

    closing = client.post(
        f"/api/v1/milestones/{a['id']}/dependencies",
        headers=auth(world.faculty),
        json={"depends_on_id": c["id"]},
    )
    assert closing.status_code == 409


def test_a_milestone_cannot_wait_on_another_projects_work(client: TestClient, world: World) -> None:
    mine = add_milestone(client, world)
    theirs = client.post(
        f"/api/v1/projects/{world.draft_project_id}/milestones",
        headers=auth(world.other_faculty),
        json={"title": "Elsewhere", "due_date": day(5)},
    ).json()
    response = client.post(
        f"/api/v1/milestones/{mine['id']}/dependencies",
        headers=auth(world.faculty),
        json={"depends_on_id": theirs["id"]},
    )
    assert response.status_code == 422


def test_removing_a_dependency_unblocks(client: TestClient, world: World) -> None:
    late = add_milestone(client, world, title="Late", due=-5)
    blocked = add_milestone(client, world, title="Waiting", due=60)
    client.post(
        f"/api/v1/milestones/{blocked['id']}/dependencies",
        headers=auth(world.faculty),
        json={"depends_on_id": late["id"]},
    )
    freed = client.delete(
        f"/api/v1/milestones/{blocked['id']}/dependencies/{late['id']}",
        headers=auth(world.faculty),
    ).json()
    assert freed["risk"] == "on_track"
    assert freed["depends_on"] == []


# --- the caller's own view -------------------------------------------------


def test_my_milestones_lists_outstanding_work_soonest_first(
    client: TestClient, world: World
) -> None:
    add_milestone(client, world, title="Later", due=40)
    add_milestone(client, world, title="Sooner", due=5)
    finished = add_milestone(client, world, title="Finished", due=1)
    client.post(
        f"/api/v1/milestones/{finished['id']}/status",
        headers=auth(world.faculty),
        json={"status": "done"},
    )

    mine = client.get("/api/v1/me/milestones", headers=auth(world.faculty)).json()
    assert [m["title"] for m in mine] == ["Sooner", "Later"]
    assert mine[0]["project_title"]


def test_my_milestones_is_empty_for_somebody_with_no_projects(
    client: TestClient, world: World
) -> None:
    assert client.get("/api/v1/me/milestones", headers=auth(world.student)).json() == []


# --- the at-risk board -----------------------------------------------------


def test_the_board_groups_by_project_and_counts_each_kind(client: TestClient, world: World) -> None:
    add_milestone(client, world, title="Late one", due=-4)
    add_milestone(client, world, title="Late two", due=-1)
    add_milestone(client, world, title="Soon", due=3)
    add_milestone(client, world, title="Fine", due=90)

    board = client.get(
        "/api/v1/coordinator/at-risk-projects", headers=auth(world.coordinator)
    ).json()
    assert len(board) == 1
    entry = board[0]
    assert entry["project_id"] == world.project_id
    assert entry["overdue_count"] == 2
    assert entry["at_risk_count"] == 1
    # The healthy one is not on a board about things needing attention.
    assert {m["title"] for m in entry["milestones"]} == {"Late one", "Late two", "Soon"}


def test_a_project_with_nothing_slipping_is_not_on_the_board(
    client: TestClient, world: World
) -> None:
    add_milestone(client, world, title="Comfortable", due=120)
    board = client.get(
        "/api/v1/coordinator/at-risk-projects", headers=auth(world.coordinator)
    ).json()
    assert board == []


def test_the_board_is_not_for_students(client: TestClient, world: World) -> None:
    response = client.get("/api/v1/coordinator/at-risk-projects", headers=auth(world.student))
    assert response.status_code == 403


def test_analytics_reports_adherence(client: TestClient, world: World) -> None:
    add_milestone(client, world, title="Late", due=-2)
    add_milestone(client, world, title="Fine", due=120)
    overview = client.get("/api/v1/analytics/overview", headers=auth(world.coordinator)).json()
    adherence = overview["milestone_adherence"]
    assert adherence["overdue"] == 1
    assert adherence["on_track"] == 1


def test_signing_in_is_required(client: TestClient, world: World) -> None:
    assert client.get(f"/api/v1/projects/{world.project_id}/milestones").status_code == 401
    assert client.get(f"/api/v1/milestones/{uuid.uuid4()}").status_code == 401
