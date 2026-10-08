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
    """A patent already filed somewhere -- the "record it" entry point."""
    body: dict[str, object] = {
        "title": "A borewell rescue robot with a self-centring gripper",
        "abstract": "A tracked robot that descends a borewell and retrieves a child.",
        "jurisdiction": "IN",
        "already_filed": True,
        "filing_date": FILED,
        "application_number": f"2026{uuid.uuid4().hex[:8]}",
        "assignee": "Lovely Professional University",
        "inventors": [{"external_name": "A. Inventor"}],
    }
    body.update(overrides)
    return body


def a_disclosure(**overrides: object) -> dict[str, object]:
    """An invention put to the university -- the "file it for me" entry point."""
    body: dict[str, object] = {
        "title": "A borewell rescue robot with a self-centring gripper",
        "jurisdiction": "IN",
        "problem_statement": "Children fall into uncovered borewells and cannot be reached.",
        "novelty": "The gripper centres itself against an irregular shaft wall.",
        "known_prior_art": "Rigid-arm retrieval rigs, which jam in a non-circular shaft.",
        "funding_source": "DST SERB core research grant",
        "inventors": [{"external_name": "A. Inventor"}],
    }
    body.update(overrides)
    return body


def disclose(client: TestClient, user: SeededUser, **overrides: object) -> dict[str, object]:
    response = client.post("/api/v1/patents", json=a_disclosure(**overrides), headers=auth(user))
    assert response.status_code == 201, response.text
    return response.json()


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


def test_a_recorded_patent_starts_filed_whatever_the_office_has_done(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    # A granted patent is recorded by filing it and moving it along, so the
    # record carries its own history rather than appearing fully formed.
    patent = create(client, seed_user(UserRole.FACULTY))
    assert patent["status"] == "filed"
    assert patent["grant_date"] is None
    assert sorted(patent["next_statuses"]) == ["published", "rejected", "withdrawn"]
    # Nothing was put to the university, so there is no docket to quote.
    assert patent["reference"] is None


def test_an_invention_put_to_the_university_starts_disclosed_with_a_docket(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    disclosure = disclose(client, seed_user(UserRole.STUDENT))
    assert disclosure["status"] == "disclosed"
    assert disclosure["filing_date"] is None
    assert disclosure["reference"].startswith("LPU/IDF/")
    # The inventor may withdraw it and nothing else; assessing is the IP cell's.
    assert disclosure["next_statuses"] == ["withdrawn"]


def test_dockets_are_allocated_in_sequence_and_never_reused(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    # An inventor quotes this down a phone; a reference that has ever been
    # quoted must never point at a different invention.
    student = seed_user(UserRole.STUDENT)
    first = disclose(client, student)["reference"]
    second = disclose(client, student, title="A different invention entirely")["reference"]
    assert int(second.rsplit("/", 1)[1]) == int(first.rsplit("/", 1)[1]) + 1


def test_a_disclosure_may_not_carry_a_filing_date(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    # Nothing inside the university has one: the office sets it.
    response = client.post(
        "/api/v1/patents",
        json=a_disclosure(filing_date=FILED),
        headers=auth(seed_user(UserRole.STUDENT)),
    )
    assert response.status_code == 422


def test_recording_an_already_filed_patent_needs_its_filing_date(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    body = a_patent()
    del body["filing_date"]
    response = client.post("/api/v1/patents", json=body, headers=auth(seed_user(UserRole.FACULTY)))
    assert response.status_code == 422


def test_the_ip_cell_walks_a_disclosure_through_to_filing(
    client: TestClient, seed_user: Callable[..., SeededUser], department: uuid.UUID
) -> None:
    student = seed_user(UserRole.STUDENT, department_id=department)
    cell = seed_user(UserRole.RESEARCH_COORDINATOR, department_id=department)
    disclosure = disclose(client, student)
    url = f"/api/v1/patents/{disclosure['id']}/status"

    assessing = client.post(url, json={"status": "under_assessment"}, headers=auth(cell))
    assert assessing.status_code == 200

    approved = client.post(
        url,
        json={"status": "approved_to_file", "note": "Patentable; worth the fee."},
        headers=auth(cell),
    )
    assert approved.status_code == 200
    assert approved.json()["assessment_note"] == "Patentable; worth the fee."
    assert approved.json()["assessed_by_name"] == f"Seeded {cell.role.value}"

    filed = client.post(
        url,
        json={"status": "filed", "on": "2026-03-01", "number": "202641000999"},
        headers=auth(student),
    )
    assert filed.status_code == 200
    assert filed.json()["filing_date"] == "2026-03-01"
    assert filed.json()["application_number"] == "202641000999"


def test_an_inventor_cannot_assess_their_own_disclosure(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    # The move exists; it is simply not theirs. 403, not 409.
    student = seed_user(UserRole.STUDENT)
    disclosure = disclose(client, student)
    response = client.post(
        f"/api/v1/patents/{disclosure['id']}/status",
        json={"status": "under_assessment"},
        headers=auth(student),
    )
    assert response.status_code == 403


def test_declining_without_a_reason_is_refused(
    client: TestClient, seed_user: Callable[..., SeededUser], department: uuid.UUID
) -> None:
    # "No" with no reason is what stops the next person disclosing.
    student = seed_user(UserRole.STUDENT, department_id=department)
    cell = seed_user(UserRole.RESEARCH_COORDINATOR, department_id=department)
    disclosure = disclose(client, student)
    url = f"/api/v1/patents/{disclosure['id']}/status"
    client.post(url, json={"status": "under_assessment"}, headers=auth(cell))

    bare = client.post(url, json={"status": "declined"}, headers=auth(cell))
    assert bare.status_code == 422

    reasoned = client.post(
        url,
        json={"status": "declined", "note": "Disclosed at a conference last year."},
        headers=auth(cell),
    )
    assert reasoned.status_code == 200
    assert reasoned.json()["assessment_note"] == "Disclosed at a conference last year."


def test_an_assessment_can_be_sent_back_for_more_detail(
    client: TestClient, seed_user: Callable[..., SeededUser], department: uuid.UUID
) -> None:
    student = seed_user(UserRole.STUDENT, department_id=department)
    cell = seed_user(UserRole.RESEARCH_COORDINATOR, department_id=department)
    disclosure = disclose(client, student)
    url = f"/api/v1/patents/{disclosure['id']}/status"
    client.post(url, json={"status": "under_assessment"}, headers=auth(cell))
    back = client.post(
        url,
        json={"status": "disclosed", "note": "Please say what the gripper does differently."},
        headers=auth(cell),
    )
    assert back.status_code == 200
    assert back.json()["status"] == "disclosed"


def test_a_public_disclosure_date_is_carried_through_to_the_assessor(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    # The field that most often decides whether a patent is possible at all.
    disclosure = disclose(
        client,
        seed_user(UserRole.STUDENT),
        public_disclosure_date="2025-11-02",
        public_disclosure_note="Presented as a poster at a departmental symposium.",
    )
    assert disclosure["public_disclosure_date"] == "2025-11-02"
    assert "poster" in disclosure["public_disclosure_note"]


def test_a_disclosure_appears_in_the_ip_cells_queue(
    client: TestClient, seed_user: Callable[..., SeededUser], department: uuid.UUID
) -> None:
    student = seed_user(UserRole.STUDENT, department_id=department)
    cell = seed_user(UserRole.RESEARCH_COORDINATOR, department_id=department)
    disclosure = disclose(client, student)
    queue = client.get("/api/v1/patent-review-queue", headers=auth(cell))
    assert disclosure["id"] in [row["id"] for row in queue.json()]


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
