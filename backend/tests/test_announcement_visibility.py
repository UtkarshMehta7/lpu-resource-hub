"""Who sees a notice, and the unread count that follows from it.

Reading the board needs no permission -- that is the feature. A student, a
facility custodian and the dean read the same page, and there is no role
filter anywhere in the module. What IS scoped is the reach of the poster, so
these tests are mostly about departments rather than roles.

The unread count is the other half. One post writes ONE row, and the count is
a NOT EXISTS against `announcement_reads`, so these also pin that reading a
notice is what clears it -- not a fan-out at post time.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.users.models import CoordinatorScopeType, UserRole
from tests.conftest import SeededUser
from tests.test_announcements import post_draft, publish
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


def board_ids(client: TestClient, viewer: SeededUser) -> list[str]:
    response = client.get("/api/v1/announcements", headers=auth(viewer), params={"page_size": 100})
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def unread(client: TestClient, viewer: SeededUser) -> int:
    response = client.get("/api/v1/announcements/unread-count", headers=auth(viewer))
    assert response.status_code == 200, response.text
    return int(response.json()["unread"])


def institution_notice(client: TestClient, world: World) -> str:
    notice = post_draft(client, world.admin, subject="Holiday on Monday")
    publish(client, world.admin, notice["id"])
    return str(notice["id"])


def department_notice(client: TestClient, world: World) -> str:
    notice = post_draft(client, world.coordinator, subject="Department seminar")
    publish(client, world.coordinator, notice["id"])
    return str(notice["id"])


def second_department(client: TestClient, world: World) -> str:
    school_id = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "School of Pharmacy"}
    ).json()["id"]
    return str(
        client.post(
            "/api/v1/admin/departments",
            headers=auth(world.admin),
            json={"school_id": school_id, "name": "Pharmaceutics"},
        ).json()["id"]
    )


# ----------------------------------------------- an institution-wide notice


@pytest.mark.parametrize("role_name", ["student", "faculty", "coordinator", "admin"])
def test_every_role_reads_an_institution_wide_notice(
    client: TestClient, world: World, role_name: str
) -> None:
    notice_id = institution_notice(client, world)
    viewer: SeededUser = getattr(world, role_name)

    assert notice_id in board_ids(client, viewer)


def test_a_custodian_reads_the_board_too(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """The role that had no dashboard section for days.

    A custodian holds two permissions and neither is about notices, which is
    exactly why this is asserted: reading the board must not have quietly
    acquired a permission check.
    """
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)
    notice_id = institution_notice(client, world)

    assert notice_id in board_ids(client, custodian)


def test_a_dean_reads_the_board_too(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)
    notice_id = institution_notice(client, world)

    assert notice_id in board_ids(client, dean)


def test_a_person_with_no_department_still_reads_institution_notices(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """An administrator belongs to no department, and nor need anyone else.

    `department_id` is nullable for every role, and the departmental branch of
    the filter compares against it -- so a null must not accidentally exclude
    somebody from the notices that are addressed to everybody.
    """
    unattached = seed_user(UserRole.FACULTY, department_id=None)
    notice_id = institution_notice(client, world)

    assert notice_id in board_ids(client, unattached)


def test_reading_the_board_requires_signing_in(client: TestClient) -> None:
    assert client.get("/api/v1/announcements").status_code == 401


# ---------------------------------------------------- a departmental notice


@pytest.mark.parametrize("role_name", ["student", "faculty"])
def test_the_department_reads_its_own_notice(
    client: TestClient, world: World, role_name: str
) -> None:
    notice_id = department_notice(client, world)
    viewer: SeededUser = getattr(world, role_name)

    assert notice_id in board_ids(client, viewer)


def test_another_department_does_not(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    other_department_id = second_department(client, world)
    outsider = seed_user(UserRole.STUDENT, department_id=other_department_id)
    notice_id = department_notice(client, world)

    assert notice_id not in board_ids(client, outsider)


def test_another_departments_notice_is_404_and_not_403(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """404, so the board never confirms that a notice exists elsewhere.

    403 would tell a student that the department they are not in has notices,
    which is the one thing the scoping is for.
    """
    other_department_id = second_department(client, world)
    outsider = seed_user(UserRole.STUDENT, department_id=other_department_id)
    notice_id = department_notice(client, world)

    assert (
        client.get(f"/api/v1/announcements/{notice_id}", headers=auth(outsider)).status_code == 404
    )


def test_a_person_with_no_department_sees_no_departmental_notice(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    unattached = seed_user(UserRole.FACULTY, department_id=None)
    notice_id = department_notice(client, world)

    assert notice_id not in board_ids(client, unattached)


def test_an_admin_sees_every_departments_notices(client: TestClient, world: World) -> None:
    """An administrator answers for the board, so they read all of it."""
    notice_id = department_notice(client, world)

    assert notice_id in board_ids(client, world.admin)


def test_a_dean_sees_every_departments_notices(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """A dean oversees every department (INSTITUTION_WIDE_ROLES).

    Withholding a department's notices from them would be a gap in the model,
    not a privacy guarantee -- the same reasoning as the cross-department
    review queue in ADR 0032.
    """
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)
    notice_id = department_notice(client, world)

    assert notice_id in board_ids(client, dean)


def test_a_coordinator_does_not_see_another_departments_notice(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """A coordinator is scoped, institution-wide roles are not.

    This is the test that fails if somebody folds coordinators into
    INSTITUTION_WIDE_ROLES to "simplify" the filter.
    """
    other_department_id = second_department(client, world)
    other_coordinator = seed_user(
        UserRole.RESEARCH_COORDINATOR,
        department_id=other_department_id,
        coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
        coordinator_scope_id=other_department_id,
    )
    notice_id = department_notice(client, world)

    assert notice_id not in board_ids(client, other_coordinator)


# ------------------------------------------------------------------- drafts


def test_an_author_sees_their_own_draft(client: TestClient, world: World) -> None:
    notice = post_draft(client, world.coordinator)

    assert notice["id"] in board_ids(client, world.coordinator)


def test_nobody_else_sees_a_draft_including_an_admin(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """The form tells the author nobody else can see it, so that must be true.

    An administrator is included. They answer for the BOARD -- which is what
    withdrawing is for -- not for somebody's unfinished sentences. The same
    answer a conversation thread gives a non-participant, admins included.
    """
    notice = post_draft(client, world.coordinator)
    other = seed_user(
        UserRole.RESEARCH_COORDINATOR,
        department_id=world.department_id,
        coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
        coordinator_scope_id=world.department_id,
    )

    assert notice["id"] not in board_ids(client, world.student)
    assert notice["id"] not in board_ids(client, other)
    assert notice["id"] not in board_ids(client, world.admin)
    assert (
        client.get(f"/api/v1/announcements/{notice['id']}", headers=auth(world.admin)).status_code
        == 404
    )


def test_an_admin_can_still_see_a_withdrawn_notice(client: TestClient, world: World) -> None:
    """So there is somebody able to clear one away.

    `may_delete` lets an admin remove a withdrawn notice; a filter that hid it
    from them would make that a dead route.
    """
    notice_id = department_notice(client, world)
    client.post(f"/api/v1/announcements/{notice_id}/withdraw", headers=auth(world.admin))

    assert notice_id in board_ids(client, world.admin)
    assert notice_id not in board_ids(client, world.student)


def test_mine_lists_only_my_own(client: TestClient, world: World) -> None:
    mine = post_draft(client, world.coordinator, subject="Mine")
    institution_notice(client, world)

    response = client.get(
        "/api/v1/announcements", headers=auth(world.coordinator), params={"mine": True}
    ).json()

    assert [item["id"] for item in response["items"]] == [mine["id"]]


# ------------------------------------------------------------ unread counts


def test_a_new_notice_is_unread(client: TestClient, world: World) -> None:
    institution_notice(client, world)

    assert unread(client, world.student) == 1


def test_a_draft_counts_for_nobody(client: TestClient, world: World) -> None:
    """Including its author: an unread badge on your own unfinished draft is
    a notification from yourself."""
    post_draft(client, world.coordinator)

    assert unread(client, world.student) == 0
    assert unread(client, world.coordinator) == 0


def test_reading_a_notice_clears_it(client: TestClient, world: World) -> None:
    notice_id = institution_notice(client, world)

    assert (
        client.post(
            f"/api/v1/announcements/{notice_id}/read", headers=auth(world.student)
        ).status_code
        == 204
    )
    assert unread(client, world.student) == 0


def test_reading_it_twice_is_harmless(client: TestClient, world: World) -> None:
    """Two tabs opening the same notice together race on the primary key.

    ON CONFLICT DO NOTHING is what makes the second one a no-op rather than a
    500, which a read-then-insert would have been.
    """
    notice_id = institution_notice(client, world)

    client.post(f"/api/v1/announcements/{notice_id}/read", headers=auth(world.student))
    second = client.post(f"/api/v1/announcements/{notice_id}/read", headers=auth(world.student))

    assert second.status_code == 204
    assert unread(client, world.student) == 0


def test_one_person_reading_it_does_not_clear_it_for_another(
    client: TestClient, world: World
) -> None:
    notice_id = institution_notice(client, world)

    client.post(f"/api/v1/announcements/{notice_id}/read", headers=auth(world.student))

    assert unread(client, world.faculty) == 1


def test_the_count_only_counts_what_is_addressed_to_you(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    other_department_id = second_department(client, world)
    outsider = seed_user(UserRole.STUDENT, department_id=other_department_id)
    institution_notice(client, world)
    department_notice(client, world)

    assert unread(client, world.student) == 2
    assert unread(client, outsider) == 1


def test_marking_an_invisible_notice_read_is_404(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """Otherwise the read endpoint is an oracle for which notices exist."""
    other_department_id = second_department(client, world)
    outsider = seed_user(UserRole.STUDENT, department_id=other_department_id)
    notice_id = department_notice(client, world)

    assert (
        client.post(f"/api/v1/announcements/{notice_id}/read", headers=auth(outsider)).status_code
        == 404
    )


def test_withdrawing_a_notice_removes_it_from_the_count(client: TestClient, world: World) -> None:
    notice_id = institution_notice(client, world)
    assert unread(client, world.student) == 1

    client.post(f"/api/v1/announcements/{notice_id}/withdraw", headers=auth(world.admin))

    assert unread(client, world.student) == 0


def test_unread_only_filters_the_board(client: TestClient, world: World) -> None:
    first = institution_notice(client, world)
    second = post_draft(client, world.admin, subject="A second notice")
    publish(client, world.admin, second["id"])
    client.post(f"/api/v1/announcements/{first}/read", headers=auth(world.student))

    response = client.get(
        "/api/v1/announcements", headers=auth(world.student), params={"unread_only": True}
    ).json()

    assert [item["id"] for item in response["items"]] == [second["id"]]


def test_the_unread_flag_rides_on_each_row(client: TestClient, world: World) -> None:
    """So the board can mark them without a request per notice."""
    notice_id = institution_notice(client, world)

    before = client.get("/api/v1/announcements", headers=auth(world.student)).json()
    assert before["items"][0]["unread"] is True

    client.post(f"/api/v1/announcements/{notice_id}/read", headers=auth(world.student))
    after = client.get("/api/v1/announcements", headers=auth(world.student)).json()
    assert after["items"][0]["unread"] is False


# ------------------------------------------------------------------- search


def test_the_board_is_searchable(client: TestClient, world: World) -> None:
    wanted = post_draft(
        client,
        world.admin,
        subject="Patent disclosure window",
        body="Send your invention disclosures to the IP cell.",
    )
    publish(client, world.admin, wanted["id"])
    other = post_draft(
        client, world.admin, subject="Canteen timings", body="The canteen shuts at six."
    )
    publish(client, world.admin, other["id"])

    response = client.get(
        "/api/v1/announcements", headers=auth(world.student), params={"q": "disclosure"}
    ).json()

    assert [item["id"] for item in response["items"]] == [wanted["id"]]


def test_search_respects_visibility(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """A query must not become a way around the department scope."""
    other_department_id = second_department(client, world)
    outsider = seed_user(UserRole.STUDENT, department_id=other_department_id)
    notice = post_draft(client, world.coordinator, subject="Seminar on photonics")
    publish(client, world.coordinator, notice["id"])

    response = client.get(
        "/api/v1/announcements", headers=auth(outsider), params={"q": "photonics"}
    ).json()

    assert response["items"] == []


# ----------------------------------------------------- the dashboard panel


def dashboard(client: TestClient, viewer: SeededUser) -> dict:
    response = client.get("/api/v1/me/dashboard", headers=auth(viewer))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("role_name", ["student", "faculty", "coordinator", "admin"])
def test_every_role_gets_the_panel(client: TestClient, world: World, role_name: str) -> None:
    """Outside the per-role dispatch, because a notice is for everybody.

    The dashboard is where people actually meet the board, so a role that
    did not get the panel would never see a notice at all.
    """
    institution_notice(client, world)
    viewer: SeededUser = getattr(world, role_name)

    panel = dashboard(client, viewer)["announcements"]

    assert panel["unread"] == 1
    assert len(panel["latest"]) == 1


def test_a_custodian_and_a_dean_get_it_too(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """The two roles outside the provisioning chain, which have been
    forgotten on the dashboard before."""
    institution_notice(client, world)
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)

    assert len(dashboard(client, custodian)["announcements"]["latest"]) == 1
    assert len(dashboard(client, dean)["announcements"]["latest"]) == 1


def test_the_panel_is_scoped_like_the_board(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """It must not become a way round the department scope."""
    other_department_id = second_department(client, world)
    outsider = seed_user(UserRole.STUDENT, department_id=other_department_id)
    institution_notice(client, world)
    department_notice(client, world)

    assert len(dashboard(client, world.student)["announcements"]["latest"]) == 2
    assert len(dashboard(client, outsider)["announcements"]["latest"]) == 1


def test_the_panel_holds_only_published_notices(client: TestClient, world: World) -> None:
    """Including the author's own draft: an unfinished notice of your own on
    your own dashboard is noise, and it is reachable from the history."""
    post_draft(client, world.coordinator)

    panel = dashboard(client, world.coordinator)["announcements"]

    assert panel["latest"] == []
    assert panel["unread"] == 0


def test_the_panel_is_newest_first_and_short(client: TestClient, world: World) -> None:
    """A dashboard section, not the whole board -- the history is for that."""
    subjects = [f"Notice number {index}" for index in range(6)]
    for subject in subjects:
        notice = post_draft(client, world.admin, subject=subject)
        publish(client, world.admin, notice["id"])

    panel = dashboard(client, world.student)["announcements"]

    assert [item["subject"] for item in panel["latest"]] == subjects[:-5:-1]
    # Every one of them is still counted, even though only a few are shown.
    assert panel["unread"] == len(subjects)


def test_reading_one_lowers_the_dashboard_count(client: TestClient, world: World) -> None:
    notice_id = institution_notice(client, world)
    assert dashboard(client, world.student)["announcements"]["unread"] == 1

    client.post(f"/api/v1/announcements/{notice_id}/read", headers=auth(world.student))

    assert dashboard(client, world.student)["announcements"]["unread"] == 0
