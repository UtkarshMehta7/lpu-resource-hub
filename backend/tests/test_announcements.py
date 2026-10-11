"""Posting a notice: who may, how far it carries, and what cannot be unsaid.

The reach is the part worth pinning. It is DERIVED from the poster, so there
is no `audience` field for a coordinator to set to "institution" -- and these
tests assert the derivation rather than trusting the schema to have no such
field, because a later change could add one back without any test noticing.
"""

from __future__ import annotations

import uuid
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


def post_draft(
    client: TestClient,
    actor: SeededUser,
    *,
    subject: str = "Disclosure window closes on Friday",
    body: str = "Send invention disclosures to the IP cell before 5 pm on Friday.",
    links: list[dict[str, str]] | None = None,
) -> dict:
    response = client.post(
        "/api/v1/announcements",
        headers=auth(actor),
        json={"subject": subject, "body": body, "links": links or []},
    )
    assert response.status_code == 201, response.text
    return response.json()


def publish(client: TestClient, actor: SeededUser, announcement_id: str) -> int:
    return client.post(
        f"/api/v1/announcements/{announcement_id}/publish", headers=auth(actor)
    ).status_code


# ------------------------------------------------------------ who may post


@pytest.mark.parametrize("role_name", ["admin", "coordinator"])
def test_the_posting_roles_may_post(client: TestClient, world: World, role_name: str) -> None:
    actor: SeededUser = getattr(world, role_name)

    assert post_draft(client, actor)["status"] == "draft"


def test_a_dean_may_post(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """The one thing a dean writes.

    ADR 0028 made the role deliberately read-only, which left somebody senior
    able to see the whole institution and unable to tell it anything.
    """
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)

    assert post_draft(client, dean)["audience"] == "institution"


@pytest.mark.parametrize("role_name", ["faculty", "student"])
def test_the_other_roles_may_not_post(client: TestClient, world: World, role_name: str) -> None:
    """Faculty must not pick this up by inheritance.

    RESEARCH_COORDINATOR inherits FACULTY, so a permission granted at the
    faculty level reaches the coordinator -- but not the reverse. This asserts
    the grant went on the right rung.
    """
    actor: SeededUser = getattr(world, role_name)

    response = client.post(
        "/api/v1/announcements",
        headers=auth(actor),
        json={"subject": "Hello everyone", "body": "Please read this."},
    )

    assert response.status_code == 403


def test_a_custodian_may_not_post(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)

    response = client.post(
        "/api/v1/announcements",
        headers=auth(custodian),
        json={"subject": "Lab closed", "body": "The lab is shut on Monday."},
    )

    assert response.status_code == 403


def test_posting_requires_signing_in(client: TestClient) -> None:
    assert (
        client.post("/api/v1/announcements", json={"subject": "x", "body": "y"}).status_code == 401
    )


# --------------------------------------------------------------- the reach


def test_an_admin_addresses_the_institution(client: TestClient, world: World) -> None:
    notice = post_draft(client, world.admin)

    assert notice["audience"] == "institution"
    assert notice["department_id"] is None


def test_a_coordinator_addresses_their_own_department(client: TestClient, world: World) -> None:
    notice = post_draft(client, world.coordinator)

    assert notice["audience"] == "department"
    assert notice["department_id"] == world.department_id
    assert notice["department_name"] == "Agriculture"


def test_a_coordinator_cannot_ask_for_a_wider_audience(client: TestClient, world: World) -> None:
    """The field does not exist, and sending it anyway changes nothing.

    This is the test that would fail if somebody added an `audience` field to
    the create schema "to validate it" -- the same mistake the create-account
    body is protected from.
    """
    response = client.post(
        "/api/v1/announcements",
        headers=auth(world.coordinator),
        json={
            "subject": "Everyone please note",
            "body": "A notice meant for the whole university.",
            "audience": "institution",
            "department_id": None,
        },
    )

    assert response.status_code == 201
    assert response.json()["audience"] == "department"
    assert response.json()["department_id"] == world.department_id


def test_a_coordinator_with_no_scope_is_refused_rather_than_widened(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """A notice addressed to nobody must fail loudly.

    `_sync_coordinator_scope` makes this unreachable through the application,
    but a row written by a script could still be in this state, and the wrong
    answer here is to quietly promote the notice to institution-wide.
    """
    unscoped = seed_user(UserRole.RESEARCH_COORDINATOR, department_id=world.department_id)

    response = client.post(
        "/api/v1/announcements",
        headers=auth(unscoped),
        json={"subject": "Notice", "body": "Body text."},
    )

    assert response.status_code == 409
    assert "coordinator scope" in response.json()["error"]["message"]


def test_the_poster_is_frozen_on_the_notice(client: TestClient, world: World) -> None:
    """ "From the Dean of Research" is part of what was said.

    Both the name and the role are copied onto the row, so promoting that
    person later does not retitle a notice they posted last term.
    """
    notice = post_draft(client, world.coordinator)

    assert notice["posted_by"] == str(world.coordinator.id)
    assert notice["posted_by_role"] == "research_coordinator"
    assert notice["posted_by_name"] == "Seeded research_coordinator"


# ------------------------------------------------------------- the lifecycle


def test_a_draft_reaches_nobody_until_it_is_published(client: TestClient, world: World) -> None:
    notice = post_draft(client, world.admin)

    board = client.get("/api/v1/announcements", headers=auth(world.student)).json()

    assert notice["id"] not in [item["id"] for item in board["items"]]


def test_publishing_puts_it_on_the_board_and_dates_it(client: TestClient, world: World) -> None:
    notice = post_draft(client, world.admin)

    assert publish(client, world.admin, notice["id"]) == 200

    published = client.get(
        f"/api/v1/announcements/{notice['id']}", headers=auth(world.student)
    ).json()
    assert published["status"] == "published"
    # The CHECK requires it; this asserts the service actually sets it rather
    # than the constraint being the only thing standing between us and a
    # published notice with no date.
    assert published["published_at"] is not None


def test_a_published_notice_cannot_be_edited_even_by_its_author(
    client: TestClient, world: World
) -> None:
    """409, not 403.

    The move does not exist for anybody -- the institution has already read
    it. Answering 403 would tell the author it was merely above their pay
    grade, which is the ordering mistake the patent pipeline documents.
    """
    notice = post_draft(client, world.admin)
    publish(client, world.admin, notice["id"])

    response = client.patch(
        f"/api/v1/announcements/{notice['id']}",
        headers=auth(world.admin),
        json={"subject": "Actually, next Friday"},
    )

    assert response.status_code == 409


def test_somebody_elses_draft_is_not_found_rather_than_forbidden(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """A draft is invisible, so editing it answers 404 and not 403.

    403 would confirm the notice exists, which is the thing a draft is not
    supposed to do.
    """
    other = seed_user(
        UserRole.RESEARCH_COORDINATOR,
        department_id=world.department_id,
        coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
        coordinator_scope_id=world.department_id,
    )
    notice = post_draft(client, other)

    response = client.patch(
        f"/api/v1/announcements/{notice['id']}",
        headers=auth(world.coordinator),
        json={"subject": "Mine now"},
    )

    assert response.status_code == 404


def test_an_admin_may_withdraw_somebody_elses_notice(client: TestClient, world: World) -> None:
    notice = post_draft(client, world.coordinator)
    publish(client, world.coordinator, notice["id"])

    response = client.post(
        f"/api/v1/announcements/{notice['id']}/withdraw", headers=auth(world.admin)
    )

    assert response.status_code == 200
    assert response.json()["status"] == "withdrawn"


def test_an_admin_can_never_rewrite_somebody_elses_words(client: TestClient, world: World) -> None:
    """Taking it down and rewriting it are different powers.

    An administrator answers for the board, which is why they may withdraw.
    Changing what another person is recorded as having announced is worse than
    removing it, so there is no state in which the route succeeds: a draft is
    invisible to them (404) and a published notice is editable by nobody
    (409).
    """
    draft = post_draft(client, world.coordinator)
    rewrite = {"body": "Something the coordinator never said."}

    invisible = client.patch(
        f"/api/v1/announcements/{draft['id']}", headers=auth(world.admin), json=rewrite
    )
    assert invisible.status_code == 404

    publish(client, world.coordinator, draft["id"])
    uneditable = client.patch(
        f"/api/v1/announcements/{draft['id']}", headers=auth(world.admin), json=rewrite
    )
    assert uneditable.status_code == 409


def test_a_withdrawn_notice_leaves_the_board(client: TestClient, world: World) -> None:
    notice = post_draft(client, world.admin)
    publish(client, world.admin, notice["id"])
    client.post(f"/api/v1/announcements/{notice['id']}/withdraw", headers=auth(world.admin))

    board = client.get("/api/v1/announcements", headers=auth(world.student)).json()

    assert notice["id"] not in [item["id"] for item in board["items"]]
    assert (
        client.get(f"/api/v1/announcements/{notice['id']}", headers=auth(world.student)).status_code
        == 404
    )


def test_a_published_notice_cannot_be_deleted_outright(client: TestClient, world: World) -> None:
    """Withdraw leaves the record; delete would let somebody unsay it."""
    notice = post_draft(client, world.admin)
    publish(client, world.admin, notice["id"])

    assert (
        client.delete(
            f"/api/v1/announcements/{notice['id']}", headers=auth(world.admin)
        ).status_code
        == 409
    )


def test_an_author_may_discard_their_own_draft(client: TestClient, world: World) -> None:
    notice = post_draft(client, world.coordinator)

    assert (
        client.delete(
            f"/api/v1/announcements/{notice['id']}", headers=auth(world.coordinator)
        ).status_code
        == 204
    )


def test_a_withdrawn_notice_may_be_deleted_by_an_admin(client: TestClient, world: World) -> None:
    notice = post_draft(client, world.admin)
    publish(client, world.admin, notice["id"])
    client.post(f"/api/v1/announcements/{notice['id']}/withdraw", headers=auth(world.admin))

    assert (
        client.delete(
            f"/api/v1/announcements/{notice['id']}", headers=auth(world.admin)
        ).status_code
        == 204
    )


def test_a_missing_notice_is_404(client: TestClient, world: World) -> None:
    assert (
        client.get(f"/api/v1/announcements/{uuid.uuid4()}", headers=auth(world.student)).status_code
        == 404
    )


# -------------------------------------------------------------------- links


def test_links_are_kept_in_the_authors_order(client: TestClient, world: World) -> None:
    notice = post_draft(
        client,
        world.admin,
        links=[
            {"label": "The form", "url": "https://example.org/form"},
            {"label": "Last year's circular", "url": "https://example.org/circular"},
        ],
    )

    assert [link["label"] for link in notice["links"]] == [
        "The form",
        "Last year's circular",
    ]


def test_a_javascript_url_is_refused(client: TestClient, world: World) -> None:
    """A notice is read by the whole institution.

    So a `javascript:` URL on one is a stored script with an audience.
    Refused on the way in as well as escaped on render: either alone is a
    single point of failure.
    """
    response = client.post(
        "/api/v1/announcements",
        headers=auth(world.admin),
        json={
            "subject": "Please read",
            "body": "Click the link.",
            "links": [{"label": "Click", "url": "javascript:alert(1)"}],
        },
    )

    assert response.status_code == 422


def test_editing_replaces_the_whole_link_list(client: TestClient, world: World) -> None:
    notice = post_draft(
        client, world.admin, links=[{"label": "One", "url": "https://example.org/one"}]
    )

    updated = client.patch(
        f"/api/v1/announcements/{notice['id']}",
        headers=auth(world.admin),
        json={"links": [{"label": "Two", "url": "https://example.org/two"}]},
    ).json()

    assert [link["label"] for link in updated["links"]] == ["Two"]


def test_omitting_links_leaves_them_alone(client: TestClient, world: World) -> None:
    """Absent is not the same as empty.

    A subject-only edit must not silently drop the links, which is what a
    `default_factory=list` on the update schema would have done.
    """
    notice = post_draft(
        client, world.admin, links=[{"label": "One", "url": "https://example.org/one"}]
    )

    updated = client.patch(
        f"/api/v1/announcements/{notice['id']}",
        headers=auth(world.admin),
        json={"subject": "A clearer subject"},
    ).json()

    assert [link["label"] for link in updated["links"]] == ["One"]
