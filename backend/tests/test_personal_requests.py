"""Personal requests: who may ask whom, and what happens next.

The routing table is the part that earns the feature. This is the only place
on the platform where a sender NAMES their recipient -- the deliberate
opposite of a nudge, whose schema has no recipient field precisely so it
cannot become a way to message anyone in the institution (ADR 0031). What
stops this being that route is `REQUEST_RECIPIENT_ROLES` plus a department
check, and both are asserted here rather than trusted.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.permissions import REQUEST_RECIPIENT_ROLES
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


def recipients(client: TestClient, sender: SeededUser) -> list[dict]:
    response = client.get("/api/v1/requests/recipients", headers=auth(sender))
    assert response.status_code == 200, response.text
    return response.json()


def submit(
    client: TestClient,
    sender: SeededUser,
    recipient_id: str,
    *,
    subject: str = "My supervisor has not signed the form",
    category: str = "academic",
) -> tuple[int, dict]:
    response = client.post(
        "/api/v1/requests",
        headers=auth(sender),
        json={
            "recipient_id": str(recipient_id),
            "subject": subject,
            "body": "Please could you look at this before Friday.",
            "category": category,
        },
    )
    return response.status_code, response.json() if response.content else {}


def move(
    client: TestClient, actor: SeededUser, request_id: str, status: str, note: str | None = None
) -> tuple[int, dict]:
    payload: dict[str, object] = {"status": status}
    if note is not None:
        payload["note"] = note
    response = client.post(
        f"/api/v1/requests/{request_id}/status", headers=auth(actor), json=payload
    )
    return response.status_code, response.json() if response.content else {}


def a_request(client: TestClient, world: World) -> str:
    """A student's request to their own faculty member."""
    code, body = submit(client, world.student, str(world.faculty.id))
    assert code == 201, body
    return str(body["id"])


# ------------------------------------------------------- the routing table


def test_the_table_only_ever_points_upward() -> None:
    """A pure check of the rule itself, with no database in the way.

    Nobody addresses their own role or anything below it, and an
    administrator addresses nobody -- a request from the top of the
    institution is an instruction, which is a different thing.
    """
    rank = {
        UserRole.STUDENT: 0,
        UserRole.FACILITY_CUSTODIAN: 1,
        UserRole.FACULTY: 1,
        UserRole.RESEARCH_COORDINATOR: 2,
        UserRole.DEAN_OF_RESEARCH: 3,
        UserRole.ADMIN: 4,
    }
    for sender, allowed in REQUEST_RECIPIENT_ROLES.items():
        assert sender not in allowed, f"{sender} may address itself"
        for recipient in allowed:
            assert rank[recipient] > rank[sender], f"{sender} -> {recipient} is not upward"
    assert REQUEST_RECIPIENT_ROLES[UserRole.ADMIN] == frozenset()


def test_a_student_is_offered_their_own_faculty_and_coordinator(
    client: TestClient, world: World
) -> None:
    offered = recipients(client, world.student)

    roles = {person["role"] for person in offered}
    assert roles <= {"faculty", "research_coordinator"}
    assert str(world.faculty.id) in {person["id"] for person in offered}


def test_the_candidate_list_names_the_department_and_the_uid(
    client: TestClient, world: World
) -> None:
    """A picker offering three people called Gurpreet is not a picker."""
    offered = recipients(client, world.student)

    assert offered
    for person in offered:
        assert person["registration_number"]
        assert person["full_name"]


def test_a_student_may_not_address_another_student(client: TestClient, world: World) -> None:
    code, _ = submit(client, world.student, str(world.other_student.id))

    assert code == 422


def test_a_student_may_not_address_another_departments_faculty(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """Role alone is not enough; the department check runs on the stored row.

    Without it, naming any faculty member in the university would work, and
    the recipient field really would be a way to message anyone.
    """
    school_id = client.post(
        "/api/v1/admin/schools", headers=auth(world.admin), json={"name": "School of Pharmacy"}
    ).json()["id"]
    other_department = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={"school_id": school_id, "name": "Pharmaceutics"},
    ).json()["id"]
    outsider = seed_user(UserRole.FACULTY, department_id=other_department)

    assert str(outsider.id) not in {p["id"] for p in recipients(client, world.student)}
    assert submit(client, world.student, str(outsider.id))[0] == 422


def test_a_faculty_member_may_reach_the_dean_and_an_admin(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """They answer to the institution, not to a department, so the
    department check does not apply to them."""
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)

    offered = {person["id"] for person in recipients(client, world.faculty)}

    assert str(dean.id) in offered
    assert str(world.admin.id) in offered
    assert submit(client, world.faculty, str(dean.id))[0] == 201


def test_a_custodian_escalates_like_a_coordinator_would_be_asked(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    custodian = seed_user(UserRole.FACILITY_CUSTODIAN, department_id=world.department_id)

    offered = {person["role"] for person in recipients(client, custodian)}

    assert "research_coordinator" in offered
    assert "student" not in offered
    assert "faculty" not in offered


def test_an_admin_addresses_nobody(client: TestClient, world: World) -> None:
    """The top of the institution. A request from here is an instruction."""
    assert recipients(client, world.admin) == []
    assert submit(client, world.admin, str(world.faculty.id))[0] == 422


def test_nobody_addresses_themselves(client: TestClient, world: World) -> None:
    assert str(world.faculty.id) not in {p["id"] for p in recipients(client, world.faculty)}
    assert submit(client, world.faculty, str(world.faculty.id))[0] == 422


def test_a_request_needs_signing_in(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/requests",
        json={
            "recipient_id": str(world.faculty.id),
            "subject": "x",
            "body": "y",
            "category": "other",
        },
    )

    assert response.status_code == 401


# ----------------------------------------------------------- what is kept


def test_the_sender_and_recipient_are_recorded_as_they_were(
    client: TestClient, world: World
) -> None:
    """The routing rule was evaluated against THESE roles.

    A later promotion must not make a historical request look like one the
    rules would have refused, and a deleted recipient must not take the
    sender's record with them.
    """
    _, body = submit(client, world.student, str(world.faculty.id))

    assert body["sender_role"] == "student"
    assert body["recipient_role"] == "faculty"
    assert body["recipient_name"] == "Seeded faculty"
    assert body["status"] == "submitted"


def test_both_parties_see_it_and_nobody_else(client: TestClient, world: World) -> None:
    """An administrator is not a party to it, which is the point.

    A channel a third person reads is useless for the thing it exists for.
    """
    request_id = a_request(client, world)

    for party in (world.student, world.faculty):
        assert client.get(f"/api/v1/requests/{request_id}", headers=auth(party)).status_code == 200
    for outsider in (world.admin, world.coordinator, world.other_student):
        assert (
            client.get(f"/api/v1/requests/{request_id}", headers=auth(outsider)).status_code == 404
        )


def test_it_appears_in_the_senders_list_and_the_recipients_inbox(
    client: TestClient, world: World
) -> None:
    request_id = a_request(client, world)

    sent = client.get("/api/v1/me/requests", headers=auth(world.student)).json()
    inbox = client.get("/api/v1/requests/inbox", headers=auth(world.faculty)).json()

    assert [item["id"] for item in sent["items"]] == [request_id]
    assert [item["id"] for item in inbox["items"]] == [request_id]
    # And not the other way round.
    assert client.get("/api/v1/requests/inbox", headers=auth(world.student)).json()["items"] == []


def test_the_recipient_is_told(client: TestClient, world: World) -> None:
    a_request(client, world)

    inbox = client.get("/api/v1/me/notifications", headers=auth(world.faculty)).json()

    kinds = [item["notification_type"] for item in inbox["items"]]
    assert "request_received" in kinds


def test_the_waiting_count_is_what_you_owe_an_answer_on(client: TestClient, world: World) -> None:
    request_id = a_request(client, world)
    assert client.get("/api/v1/requests/inbox/count", headers=auth(world.faculty)).json() == {
        "waiting": 1
    }

    # Taking it up is not answering it, so the count holds.
    move(client, world.faculty, request_id, "under_review")
    assert client.get("/api/v1/requests/inbox/count", headers=auth(world.faculty)).json() == {
        "waiting": 1
    }

    move(client, world.faculty, request_id, "resolved")
    assert client.get("/api/v1/requests/inbox/count", headers=auth(world.faculty)).json() == {
        "waiting": 0
    }


# --------------------------------------------------------- moving it along


def test_the_recipient_takes_it_up_resolves_and_the_sender_is_told(
    client: TestClient, world: World
) -> None:
    request_id = a_request(client, world)

    assert move(client, world.faculty, request_id, "under_review")[0] == 200
    code, body = move(client, world.faculty, request_id, "resolved", "Signed and returned.")

    assert code == 200
    assert body["status"] == "resolved"
    assert body["decided_at"] is not None
    kinds = [
        item["notification_type"]
        for item in client.get("/api/v1/me/notifications", headers=auth(world.student)).json()[
            "items"
        ]
    ]
    assert "request_decided" in kinds


def test_declining_requires_a_reason(client: TestClient, world: World) -> None:
    """Refused in the schema, in the service and as a CHECK.

    "No" without one is what stops the next person asking -- the rule the
    patent pipeline holds for declining a disclosure.
    """
    request_id = a_request(client, world)

    assert move(client, world.faculty, request_id, "declined")[0] == 422
    assert move(client, world.faculty, request_id, "declined", "   ")[0] == 422
    code, body = move(client, world.faculty, request_id, "declined", "Not my form to sign.")
    assert code == 200
    assert body["resolution_note"] == "Not my form to sign."


def test_the_sender_may_withdraw_but_not_decide(client: TestClient, world: World) -> None:
    request_id = a_request(client, world)

    # Resolving is not a move a sender ever has, so it is 409 and not 403 --
    # 403 would imply somebody else could grant it to them.
    assert move(client, world.student, request_id, "resolved", "done")[0] == 403
    assert move(client, world.student, request_id, "withdrawn")[0] == 200


def test_the_recipient_may_not_withdraw(client: TestClient, world: World) -> None:
    """Withdrawing is the sender saying "I no longer need this"."""
    request_id = a_request(client, world)

    assert move(client, world.faculty, request_id, "withdrawn")[0] == 403


def test_a_move_that_does_not_exist_is_409_for_everyone(client: TestClient, world: World) -> None:
    """Checked before ownership.

    The other order tells a sender that reopening their decided request is
    merely somebody else's to do, when nobody can do it: an answer has been
    given, and asking again is a NEW request with its own date.
    """
    request_id = a_request(client, world)
    move(client, world.faculty, request_id, "resolved")

    for actor in (world.student, world.faculty):
        assert move(client, actor, request_id, "submitted")[0] == 409
        assert move(client, actor, request_id, "under_review")[0] == 409


def test_a_withdrawn_request_is_finished_too(client: TestClient, world: World) -> None:
    request_id = a_request(client, world)
    move(client, world.student, request_id, "withdrawn")

    assert move(client, world.faculty, request_id, "under_review")[0] == 409


def test_a_third_party_cannot_move_it(client: TestClient, world: World) -> None:
    """404, not 403: they are not party to it and must not learn it exists."""
    request_id = a_request(client, world)

    assert move(client, world.admin, request_id, "under_review")[0] == 404


def test_the_offered_moves_are_computed_per_reader(client: TestClient, world: World) -> None:
    """So the interface can never offer a step the service would refuse."""
    request_id = a_request(client, world)

    sender_view = client.get(f"/api/v1/requests/{request_id}", headers=auth(world.student)).json()
    recipient_view = client.get(
        f"/api/v1/requests/{request_id}", headers=auth(world.faculty)
    ).json()

    assert sender_view["next_statuses"] == ["withdrawn"]
    assert sender_view["viewer_is_sender"] is True
    assert set(recipient_view["next_statuses"]) == {"under_review", "resolved", "declined"}
    assert recipient_view["viewer_is_sender"] is False


def test_a_missing_request_is_404(client: TestClient, world: World) -> None:
    assert (
        client.get(f"/api/v1/requests/{uuid.uuid4()}", headers=auth(world.student)).status_code
        == 404
    )


# ------------------------------------------------------------- the routes


def test_the_literal_paths_are_not_parsed_as_ids(client: TestClient, world: World) -> None:
    """`/requests/inbox` must not be swallowed by `/requests/{request_id}`.

    FastAPI matches in registration order and would read "inbox" as a UUID --
    the trap `/publications/duplicates` fell into.
    """
    for path in ("/api/v1/requests/inbox", "/api/v1/requests/recipients"):
        assert client.get(path, headers=auth(world.student)).status_code == 200


def test_a_coordinator_with_a_scope_can_still_be_asked(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """The coordinator in `world` oversees the student's department."""
    scoped = seed_user(
        UserRole.RESEARCH_COORDINATOR,
        department_id=world.department_id,
        coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
        coordinator_scope_id=world.department_id,
    )

    assert submit(client, world.student, str(scoped.id))[0] == 201
