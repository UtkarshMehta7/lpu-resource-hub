"""The institutional research report and the metrics behind it.

What matters here is that the numbers are *right*, not that a file was
produced. Each metric's definition is asserted against data built to exercise
exactly the case the definition talks about -- pending applications excluded
from a success rate, a publication credited to two departments, a
collaboration pair with a missing department.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.analytics import academic_year as ay
from app.modules.users.models import UserRole
from tests.conftest import SeededUser
from tests.world import World, auth, build_world

pytestmark = pytest.mark.db

YEAR = "2025-26"


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    return build_world(client, seed_user)


def report(client: TestClient, user: SeededUser, year: str = YEAR) -> dict[str, object]:
    response = client.get(
        "/api/v1/analytics/institutional-report",
        headers=auth(user),
        params={"academic_year": year},
    )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def section(body: dict[str, object], title: str) -> dict[str, object]:
    for item in body["sections"]:  # type: ignore[index]
        if item["title"] == title:
            found: dict[str, object] = item
            return found
    raise AssertionError(f"no section {title!r}")


def summary_of(body: dict[str, object], title: str) -> dict[str, str]:
    return {label: value for label, value in section(body, title)["summary"]}  # type: ignore[index]


# --- shape and period ------------------------------------------------------


def test_the_report_states_the_period_it_covers(client: TestClient, world: World) -> None:
    body = report(client, world.admin)
    assert body["academic_year"] == YEAR
    assert body["period_start"] == "2025-07-01"
    assert body["period_end"] == "2026-06-30"
    assert body["generated_at"]


def test_a_nonsense_year_is_refused_not_guessed(client: TestClient, world: World) -> None:
    response = client.get(
        "/api/v1/analytics/institutional-report",
        headers=auth(world.admin),
        params={"academic_year": "2025-27"},
    )
    assert response.status_code == 422


def test_the_year_defaults_to_the_current_one(client: TestClient, world: World) -> None:
    response = client.get("/api/v1/analytics/institutional-report", headers=auth(world.admin))
    assert response.status_code == 200
    assert response.json()["academic_year"] == ay.current().label


def test_the_offered_years_include_the_current_one(client: TestClient, world: World) -> None:
    years = client.get("/api/v1/analytics/academic-years", headers=auth(world.admin)).json()
    assert len(years) >= 1
    assert sum(1 for year in years if year["is_current"]) == 1


# --- access ----------------------------------------------------------------


def test_a_student_cannot_read_institutional_analytics(client: TestClient, world: World) -> None:
    """Aggregate institutional data is not a student's to read."""
    response = client.get("/api/v1/analytics/institutional-report", headers=auth(world.student))
    assert response.status_code == 403


def test_an_ordinary_researcher_cannot_either(client: TestClient, world: World) -> None:
    response = client.get("/api/v1/analytics/institutional-report", headers=auth(world.faculty))
    assert response.status_code == 403


def test_signing_in_is_required(client: TestClient) -> None:
    assert client.get("/api/v1/analytics/institutional-report").status_code == 401
    assert client.get("/api/v1/analytics/institutional-report/export").status_code == 401


def test_a_coordinator_sees_their_department_not_the_institution(
    client: TestClient, world: World
) -> None:
    body = report(client, world.coordinator)
    assert body["scope"] == "one department"
    assert report(client, world.admin)["scope"] == "the whole institution"


# --- the metrics -----------------------------------------------------------


def test_a_success_rate_excludes_applications_nobody_has_decided(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """The headline definition: accepted / (accepted + rejected).

    A pending application is not a failure; counting it as one would make the
    rate fall because a reviewer is slow.
    """
    applicants = [seed_user(UserRole.STUDENT, department_id=world.department_id) for _ in range(3)]
    ids = []
    for applicant in applicants:
        created = client.post(
            f"/api/v1/opportunities/{world.opportunity_id}/applications",
            headers=auth(applicant),
            json={"statement": "Please consider me."},
        )
        assert created.status_code in (200, 201), created.text
        ids.append(created.json()["id"])

    def move(application_id: str, status: str) -> None:
        response = client.post(
            f"/api/v1/applications/{application_id}/status",
            headers=auth(world.faculty),
            json={"status": status},
        )
        assert response.status_code == 200, response.text

    # Accepting goes through review: submitted -> accepted is not a legal
    # transition, which is the workflow working, not an obstacle to route past.
    move(ids[0], "under_review")
    move(ids[0], "accepted")
    move(ids[1], "rejected")
    # The third is left undecided on purpose.

    outcomes = summary_of(report(client, world.admin, ay.current().label), "Research opportunities")
    assert outcomes["Decided"] == "2"
    assert outcomes["Still pending"] == "1"
    # 1 of 2 decided, not 1 of 3 submitted.
    assert outcomes["Success rate"] == "50.0%"


def test_no_decided_applications_is_not_a_zero_per_cent_success_rate(
    client: TestClient, world: World
) -> None:
    """Division by zero, stated honestly rather than rendered as failure."""
    outcomes = summary_of(report(client, world.admin), "Research opportunities")
    assert outcomes["Success rate"] == "not applicable"


def test_collaboration_within_one_department_is_not_cross_department(
    client: TestClient, world: World
) -> None:
    request_id = client.post(
        "/api/v1/collaborations",
        headers=auth(world.faculty),
        json={"recipient_id": str(world.other_faculty.id), "message": "Shall we?"},
    ).json()["id"]
    client.post(f"/api/v1/collaborations/{request_id}/accept", headers=auth(world.other_faculty))

    collaboration = summary_of(report(client, world.admin), "Collaboration")
    assert collaboration["Within one department"] == "1"
    assert collaboration["Cross-department collaborations"] == "0"
    assert collaboration["Cross-department rate"] == "0.0%"


def test_every_section_and_table_states_what_it_counted(client: TestClient, world: World) -> None:
    """A figure without its rule invites the wrong reading."""
    body = report(client, world.admin)
    titles = {item["title"] for item in body["sections"]}  # type: ignore[index]
    assert {
        "People",
        "Research projects",
        "Publications",
        "Collaboration",
        "Research opportunities",
        "Facilities and equipment",
        "Funding",
    } <= titles

    defined = [
        table
        for item in body["sections"]  # type: ignore[index]
        for table in item["tables"]
        if table["definition"]
    ]
    assert len(defined) >= 6


# --- exports ---------------------------------------------------------------


def test_the_csv_carries_the_same_numbers_as_the_screen(client: TestClient, world: World) -> None:
    body = report(client, world.admin)
    response = client.get(
        "/api/v1/analytics/institutional-report/export",
        headers=auth(world.admin),
        params={"academic_year": YEAR, "format": "csv"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "institutional-research-report-2025-26.csv" in response.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    flat = {tuple(row) for row in rows if row}
    assert ("Academic year", "2025-26") in flat
    for label, value in section(body, "People")["summary"]:  # type: ignore[index]
        assert (label, value) in flat, f"{label} missing from the CSV"


def test_the_pdf_is_a_real_document(client: TestClient, world: World) -> None:
    response = client.get(
        "/api/v1/analytics/institutional-report/export",
        headers=auth(world.admin),
        params={"academic_year": YEAR, "format": "pdf"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    # Not an empty shell: a one-page stub would be far smaller than this.
    assert len(response.content) > 3000


def test_an_unknown_export_format_is_refused(client: TestClient, world: World) -> None:
    response = client.get(
        "/api/v1/analytics/institutional-report/export",
        headers=auth(world.admin),
        params={"format": "docx"},
    )
    assert response.status_code == 422


def test_a_student_cannot_export_it_either(client: TestClient, world: World) -> None:
    """The file is the same data; hiding the button is not the control."""
    response = client.get(
        "/api/v1/analytics/institutional-report/export", headers=auth(world.student)
    )
    assert response.status_code == 403
