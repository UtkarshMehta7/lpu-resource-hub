"""Patents: recording, the office lifecycle, and the institution's approval.

Two workflows run on one record and these tests keep them apart. `status` is
where the application has got to at the patent office; `verification_status`
is whether this institution has vouched for the record. A granted patent can
still be entered with the wrong numbers, which is the whole reason the second
exists.

Driven through the API, because the point of the feature is who may do what.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.modules.users.models import UserRole
from tests.conftest import SeededUser

pytestmark = pytest.mark.db

FILED = "2026-02-01"


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture
def department(db_settings: Settings, clean_db: None) -> uuid.UUID:
    engine = create_engine(str(db_settings.database_url))
    with engine.begin() as connection:
        school_id = connection.execute(
            text("INSERT INTO schools (name) VALUES ('Engineering') RETURNING id")
        ).scalar_one()
        return connection.execute(
            text(
                "INSERT INTO departments (school_id, name) "
                "VALUES (:school, 'Mechatronics') RETURNING id"
            ),
            {"school": school_id},
        ).scalar_one()


def auth(user: SeededUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.access_token}"}


def a_patent(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "title": "A borewell rescue robot with a self-centring gripper",
        "abstract": "A tracked robot that descends a borewell and retrieves a child.",
        "jurisdiction": "IN",
        "filing_date": FILED,
        "application_number": f"2026{uuid.uuid4().hex[:8]}",
        "assignee": "Lovely Professional University",
        "inventors": [{"external_name": "A. Inventor"}],
    }
    body.update(overrides)
    return body


def create(client: TestClient, user: SeededUser, **overrides: object) -> dict[str, object]:
    response = client.post("/api/v1/patents", json=a_patent(**overrides), headers=auth(user))
    assert response.status_code == 201, response.text
    return response.json()


# --- who may record one ------------------------------------------------------


@pytest.mark.parametrize(
    "role", [UserRole.STUDENT, UserRole.FACULTY, UserRole.RESEARCH_COORDINATOR]
)
def test_the_research_chain_may_record_a_patent(
    client: TestClient, seed_user: Callable[..., SeededUser], role: UserRole
) -> None:
    # Students invent, and the university's own showcase is full of them.
    # The safeguard is the approval queue, not withholding the form.
    assert create(client, seed_user(role))["verification_status"] == "pending"


@pytest.mark.parametrize("role", [UserRole.DEAN_OF_RESEARCH, UserRole.FACILITY_CUSTODIAN])
def test_read_only_roles_may_not_record_one(
    client: TestClient, seed_user: Callable[..., SeededUser], role: UserRole
) -> None:
    # A dean reads and changes nothing, and looking after rooms confers
    # nothing else (ADR 0028). Both may still be NAMED as inventors.
    response = client.post("/api/v1/patents", json=a_patent(), headers=auth(seed_user(role)))
    assert response.status_code == 403


def test_a_dean_can_still_be_named_as_an_inventor(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    dean = seed_user(UserRole.DEAN_OF_RESEARCH)
    patent = create(client, seed_user(UserRole.FACULTY), inventors=[{"user_id": str(dean.id)}])
    assert [i["user_id"] for i in patent["inventors"]] == [str(dean.id)]


def test_everyone_signed_in_can_read_patents(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    create(client, seed_user(UserRole.FACULTY))
    for role in (UserRole.STUDENT, UserRole.DEAN_OF_RESEARCH, UserRole.FACILITY_CUSTODIAN):
        response = client.get("/api/v1/patents", headers=auth(seed_user(role)))
        assert response.status_code == 200
        assert response.json()["total"] == 1


# --- the record itself -------------------------------------------------------


def test_a_new_record_starts_filed_whatever_the_office_has_done(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    # A granted patent is recorded by filing it and moving it along, so the
    # record carries its own history rather than appearing fully formed.
    patent = create(client, seed_user(UserRole.FACULTY))
    assert patent["status"] == "filed"
    assert patent["grant_date"] is None
    assert sorted(patent["next_statuses"]) == ["published", "rejected", "withdrawn"]


def test_an_administrators_record_needs_no_verification(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    # Nobody is senior to an administrator, so a PENDING admin record would
    # ask a coordinator to vouch for their own senior.
    patent = create(client, seed_user(UserRole.ADMIN))
    assert patent["verification_status"] == "verified"
    assert patent["verified_at"] is not None


def test_a_number_is_unique_only_inside_its_jurisdiction(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    faculty = seed_user(UserRole.FACULTY)
    create(client, faculty, application_number="202141000001", jurisdiction="IN")
    # Same number, different office: a different patent.
    create(client, faculty, application_number="202141000001", jurisdiction="US")
    clash = client.post(
        "/api/v1/patents",
        json=a_patent(application_number="202141000001", jurisdiction="IN"),
        headers=auth(faculty),
    )
    assert clash.status_code == 409


def test_jurisdiction_must_be_a_two_letter_office_code(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    response = client.post(
        "/api/v1/patents",
        json=a_patent(jurisdiction="India"),
        headers=auth(seed_user(UserRole.FACULTY)),
    )
    assert response.status_code == 422


def test_lower_case_jurisdiction_is_accepted_and_stored_upper(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    assert create(client, seed_user(UserRole.FACULTY), jurisdiction="in")["jurisdiction"] == "IN"


def test_only_the_creator_may_edit(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    patent = create(client, seed_user(UserRole.FACULTY))
    response = client.patch(
        f"/api/v1/patents/{patent['id']}",
        json={"title": "Somebody else's idea"},
        headers=auth(seed_user(UserRole.FACULTY)),
    )
    assert response.status_code == 403


# --- the office's lifecycle --------------------------------------------------


def test_a_patent_walks_filed_to_published_to_granted(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    faculty = seed_user(UserRole.FACULTY)
    patent = create(client, faculty)

    published = client.post(
        f"/api/v1/patents/{patent['id']}/status",
        json={"status": "published", "on": "2026-08-01", "number": "IN202600001A"},
        headers=auth(faculty),
    )
    assert published.status_code == 200
    assert published.json()["publication_number"] == "IN202600001A"

    granted = client.post(
        f"/api/v1/patents/{patent['id']}/status",
        json={"status": "granted", "on": "2027-01-15", "number": "IN445566"},
        headers=auth(faculty),
    )
    assert granted.status_code == 200
    body = granted.json()
    assert body["status"] == "granted"
    assert body["grant_date"] == "2027-01-15"
    # Granted may only lapse from here.
    assert body["next_statuses"] == ["lapsed"]


def test_a_patent_cannot_skip_straight_to_granted(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    faculty = seed_user(UserRole.FACULTY)
    patent = create(client, faculty)
    response = client.post(
        f"/api/v1/patents/{patent['id']}/status",
        json={"status": "granted", "on": "2027-01-15"},
        headers=auth(faculty),
    )
    assert response.status_code == 409


def test_a_status_that_claims_an_event_needs_its_date(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    faculty = seed_user(UserRole.FACULTY)
    patent = create(client, faculty)
    response = client.post(
        f"/api/v1/patents/{patent['id']}/status",
        json={"status": "published"},
        headers=auth(faculty),
    )
    assert response.status_code == 422


def test_a_rejected_patent_is_terminal(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    # A fresh attempt is a new application with a new filing date, not this
    # one reopened.
    faculty = seed_user(UserRole.FACULTY)
    patent = create(client, faculty)
    client.post(
        f"/api/v1/patents/{patent['id']}/status",
        json={"status": "rejected"},
        headers=auth(faculty),
    )
    response = client.post(
        f"/api/v1/patents/{patent['id']}/status",
        json={"status": "published", "on": "2026-08-01"},
        headers=auth(faculty),
    )
    assert response.status_code == 409


def test_a_lapsed_patent_can_be_restored(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    # Paying a renewal fee late really does restore a patent.
    faculty = seed_user(UserRole.FACULTY)
    patent = create(client, faculty)
    for move in (
        {"status": "published", "on": "2026-08-01"},
        {"status": "granted", "on": "2027-01-15"},
        {"status": "lapsed"},
    ):
        client.post(f"/api/v1/patents/{patent['id']}/status", json=move, headers=auth(faculty))
    restored = client.post(
        f"/api/v1/patents/{patent['id']}/status",
        json={"status": "granted", "on": "2027-01-15"},
        headers=auth(faculty),
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "granted"


# --- the institution's approval ----------------------------------------------


def test_a_coordinator_approves_a_record_from_their_own_department(
    client: TestClient, seed_user: Callable[..., SeededUser], department: uuid.UUID
) -> None:
    student = seed_user(UserRole.STUDENT, department_id=department)
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR, department_id=department)
    patent = create(client, student)

    queue = client.get("/api/v1/patent-review-queue", headers=auth(coordinator))
    assert [row["id"] for row in queue.json()] == [patent["id"]]

    decided = client.post(
        f"/api/v1/patents/{patent['id']}/decision",
        json={"decision": True, "note": "Numbers check out against InPASS."},
        headers=auth(coordinator),
    )
    assert decided.status_code == 200
    assert decided.json()["verification_status"] == "verified"
    assert decided.json()["verified_by_name"] == coordinator_name(coordinator)


def coordinator_name(user: SeededUser) -> str:
    return f"Seeded {user.role.value}"


def test_a_coordinator_cannot_decide_another_departments_record(
    client: TestClient, seed_user: Callable[..., SeededUser], department: uuid.UUID
) -> None:
    patent = create(client, seed_user(UserRole.STUDENT))
    outsider = seed_user(UserRole.RESEARCH_COORDINATOR, department_id=department)
    response = client.post(
        f"/api/v1/patents/{patent['id']}/decision",
        json={"decision": True},
        headers=auth(outsider),
    )
    assert response.status_code == 403


def test_the_queue_only_lists_what_the_reader_could_decide(
    client: TestClient, seed_user: Callable[..., SeededUser], department: uuid.UUID
) -> None:
    # A queue that shows a record the decision would refuse is a dead button.
    create(client, seed_user(UserRole.STUDENT))
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR, department_id=department)
    assert client.get("/api/v1/patent-review-queue", headers=auth(coordinator)).json() == []


def test_a_record_is_decided_once(
    client: TestClient, seed_user: Callable[..., SeededUser], department: uuid.UUID
) -> None:
    student = seed_user(UserRole.STUDENT, department_id=department)
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR, department_id=department)
    patent = create(client, student)
    url = f"/api/v1/patents/{patent['id']}/decision"
    assert client.post(url, json={"decision": True}, headers=auth(coordinator)).status_code == 200
    assert client.post(url, json={"decision": False}, headers=auth(coordinator)).status_code == 409


def test_editing_a_verified_record_sends_it_back_for_approval(
    client: TestClient, seed_user: Callable[..., SeededUser], department: uuid.UUID
) -> None:
    # A tick means somebody checked THIS content, and the content just changed
    # -- the same rule that sends an imported profile back to pending.
    student = seed_user(UserRole.STUDENT, department_id=department)
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR, department_id=department)
    patent = create(client, student)
    client.post(
        f"/api/v1/patents/{patent['id']}/decision",
        json={"decision": True},
        headers=auth(coordinator),
    )
    edited = client.patch(
        f"/api/v1/patents/{patent['id']}",
        json={"title": "A borewell rescue robot, second revision"},
        headers=auth(student),
    )
    assert edited.json()["verification_status"] == "pending"
    assert edited.json()["verified_at"] is None


def test_a_student_cannot_approve_their_own_record(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    student = seed_user(UserRole.STUDENT)
    patent = create(client, student)
    response = client.post(
        f"/api/v1/patents/{patent['id']}/decision",
        json={"decision": True},
        headers=auth(student),
    )
    assert response.status_code == 403


def test_the_patent_is_gone_when_its_creator_is_deleted(
    client: TestClient, seed_user: Callable[..., SeededUser], db_settings: Settings
) -> None:
    faculty = seed_user(UserRole.FACULTY)
    patent = create(client, faculty)
    engine = create_engine(str(db_settings.database_url))
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": faculty.id})
    response = client.get(
        f"/api/v1/patents/{patent['id']}", headers=auth(seed_user(UserRole.FACULTY))
    )
    assert response.status_code == 404


def test_filing_date_is_required(client: TestClient, seed_user: Callable[..., SeededUser]) -> None:
    body = a_patent()
    del body["filing_date"]
    response = client.post("/api/v1/patents", json=body, headers=auth(seed_user(UserRole.FACULTY)))
    assert response.status_code == 422


def test_filtering_by_status_and_jurisdiction(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    faculty = seed_user(UserRole.FACULTY)
    create(client, faculty, jurisdiction="IN", title="Indian filing")
    create(client, faculty, jurisdiction="US", title="American filing")
    response = client.get("/api/v1/patents?jurisdiction=us", headers=auth(faculty))
    assert [row["title"] for row in response.json()["items"]] == ["American filing"]


def test_the_date_check_is_in_the_database_too(
    db_settings: Settings, clean_db: None, seed_user: Callable[..., SeededUser]
) -> None:
    """A granted patent is never undated, whatever reaches the table."""
    faculty = seed_user(UserRole.FACULTY)
    engine = create_engine(str(db_settings.database_url))
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session, pytest.raises(Exception, match="granted_has_a_grant_date"):
        session.execute(
            text(
                "INSERT INTO patents "
                "(title, jurisdiction, filing_date, status, created_by, verification_status) "
                "VALUES ('x', 'IN', :filed, 'granted', :creator, 'pending')"
            ),
            {"filed": date(2026, 2, 1), "creator": faculty.id},
        )
        session.commit()
