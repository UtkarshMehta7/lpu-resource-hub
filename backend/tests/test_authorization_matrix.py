"""Parametrized role x endpoint authorization table.

Every protected endpoint gets one row per role (plus anonymous) asserting
the exact status code. Future steps append their own endpoints to
ENDPOINTS instead of writing a new file, so this table grows every step.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.users.models import UserRole
from tests.conftest import SeededUser

pytestmark = pytest.mark.db

ALL_ROLES = (UserRole.STUDENT, UserRole.FACULTY, UserRole.RESEARCH_COORDINATOR, UserRole.ADMIN)


COORDINATOR_AND_ADMIN = frozenset({UserRole.RESEARCH_COORDINATOR, UserRole.ADMIN})


@dataclass(frozen=True, slots=True)
class Endpoint:
    method: str
    path_template: str  # "{id}" is replaced with a freshly seeded student's id
    allowed_roles: frozenset[UserRole]
    needs_target: bool = False
    body: dict[str, object] | list[object] | None = None
    # What an *authorized* caller gets. Not always 200: a create returns 201,
    # and some endpoints legitimately 404 for the generic fixture data (see
    # the comments below). The point of those rows is still authorization --
    # unauthorized roles must get 403 *before* the resource is ever looked up.
    allowed_status: int = 200


# PUT /api/v1/me/profile is deliberately absent: its request body shape
# depends on the caller's role, so one row can't express it. Its auth
# surface ("any authenticated user") is covered by GET /api/v1/me/profile.
ENDPOINTS = (
    Endpoint("GET", "/api/v1/me", frozenset(ALL_ROLES)),
    Endpoint("GET", "/api/v1/admin/users", frozenset({UserRole.ADMIN})),
    Endpoint("GET", "/api/v1/admin/audit-logs", frozenset({UserRole.ADMIN})),
    Endpoint(
        "PATCH",
        "/api/v1/admin/users/{id}",
        frozenset({UserRole.ADMIN}),
        needs_target=True,
        body={"full_name": "Updated Name"},
    ),
    Endpoint(
        "POST",
        "/api/v1/admin/users/{id}/role",
        frozenset({UserRole.ADMIN}),
        needs_target=True,
        body={"role": "faculty"},
    ),
    Endpoint(
        "POST", "/api/v1/admin/users/{id}/activate", frozenset({UserRole.ADMIN}), needs_target=True
    ),
    Endpoint(
        "POST",
        "/api/v1/admin/users/{id}/deactivate",
        frozenset({UserRole.ADMIN}),
        needs_target=True,
    ),
    Endpoint(
        "POST",
        "/api/v1/admin/users/{id}/temporary-password",
        frozenset({UserRole.ADMIN}),
        needs_target=True,
    ),
    # Removal follows the creation hierarchy. The target here is a freshly
    # seeded student with no department, so only an admin -- who is scoped to
    # everything -- reaches it; a coordinator or faculty member is refused on
    # scope, and a student has no such permission at all.
    Endpoint(
        "GET",
        "/api/v1/users/{id}/deletion-impact",
        frozenset({UserRole.ADMIN}),
        needs_target=True,
    ),
    Endpoint(
        "DELETE",
        "/api/v1/users/{id}",
        frozenset({UserRole.ADMIN}),
        needs_target=True,
        allowed_status=204,
    ),
    # Step 3: organisation
    Endpoint("GET", "/api/v1/admin/schools", frozenset({UserRole.ADMIN})),
    Endpoint(
        "POST",
        "/api/v1/admin/schools",
        frozenset({UserRole.ADMIN}),
        body={"name": "Matrix School"},
        allowed_status=201,
    ),
    Endpoint("GET", "/api/v1/admin/departments", frozenset({UserRole.ADMIN})),
    # Step 3: taxonomy
    Endpoint("GET", "/api/v1/skills", frozenset(ALL_ROLES)),
    Endpoint("GET", "/api/v1/research-areas", frozenset(ALL_ROLES)),
    Endpoint(
        "POST",
        "/api/v1/taxonomy/skills",
        COORDINATOR_AND_ADMIN,
        body={"name": "Matrix Skill"},
        allowed_status=201,
    ),
    Endpoint(
        "POST",
        "/api/v1/taxonomy/research-areas",
        COORDINATOR_AND_ADMIN,
        body={"name": "Matrix Area"},
        allowed_status=201,
    ),
    Endpoint(
        "POST",
        "/api/v1/tags/suggestions",
        frozenset(ALL_ROLES),
        body={"suggested_name": "Matrix Tag", "suggested_type": "skill"},
        allowed_status=201,
    ),
    Endpoint("GET", "/api/v1/admin/tag-suggestions", COORDINATOR_AND_ADMIN),
    # Step 3: profiles. No profile row exists for the seeded caller, so an
    # authorized caller gets 404 here.
    Endpoint("GET", "/api/v1/me/profile", frozenset(ALL_ROLES), allowed_status=404),
    Endpoint("PUT", "/api/v1/me/skills", frozenset(ALL_ROLES), body=[]),
    Endpoint("PUT", "/api/v1/me/research-areas", frozenset(ALL_ROLES), body=[]),
    # Step 3: verification. The generic target is a student with no
    # researcher profile, so an authorized reviewer gets 404.
    Endpoint("GET", "/api/v1/coordinator/verification-queue", COORDINATOR_AND_ADMIN),
    Endpoint(
        "POST",
        "/api/v1/researchers/{id}/verify",
        COORDINATOR_AND_ADMIN,
        needs_target=True,
        body={"decision": "verified"},
        allowed_status=404,
    ),
    # Step 4: directory and search
    Endpoint("GET", "/api/v1/researchers", frozenset(ALL_ROLES)),
    Endpoint("GET", "/api/v1/search?q=test", frozenset(ALL_ROLES)),
    # The generic target is a student, so there is no researcher profile to
    # show: an authorized caller legitimately gets 404.
    Endpoint(
        "GET",
        "/api/v1/researchers/{id}",
        frozenset(ALL_ROLES),
        needs_target=True,
        allowed_status=404,
    ),
    # Read-only org lists for directory filters: any signed-in user.
    Endpoint("GET", "/api/v1/schools", frozenset(ALL_ROLES)),
    Endpoint("GET", "/api/v1/departments", frozenset(ALL_ROLES)),
    # Step 5: projects. project:create is a FACULTY grant (coordinator
    # inherits it); admin deliberately doesn't author projects.
    Endpoint("GET", "/api/v1/projects", frozenset(ALL_ROLES)),
    Endpoint(
        "POST",
        "/api/v1/projects",
        frozenset({UserRole.FACULTY, UserRole.RESEARCH_COORDINATOR}),
        body={"title": "Matrix", "summary": "Matrix", "description": "Matrix"},
        allowed_status=201,
    ),
    Endpoint("GET", "/api/v1/coordinator/review-queue", COORDINATOR_AND_ADMIN),
    # The generic target id isn't a project, so an authorized reviewer gets
    # 404; everyone else must get 403 before any lookup.
    Endpoint(
        "POST",
        "/api/v1/projects/{id}/review",
        COORDINATOR_AND_ADMIN,
        needs_target=True,
        body={"decision": "approve"},
        allowed_status=404,
    ),
    # Step 6: publications are readable by everyone; publication:create is a
    # FACULTY grant (coordinator inherits it).
    Endpoint("GET", "/api/v1/publications", frozenset(ALL_ROLES)),
    Endpoint(
        "POST",
        "/api/v1/publications",
        frozenset({UserRole.FACULTY, UserRole.RESEARCH_COORDINATOR}),
        body={
            "title": "Matrix",
            "year": 2024,
            "pub_type": "journal_article",
            "authors": [{"external_name": "A. Author"}],
        },
        allowed_status=201,
    ),
    # Step 7: opportunities and applications. The random project id / target
    # id aren't real, so authorized callers get 404 -- the point is that
    # unauthorized roles get 403 first.
    Endpoint("GET", "/api/v1/opportunities", frozenset(ALL_ROLES)),
    Endpoint(
        "POST",
        "/api/v1/opportunities",
        frozenset({UserRole.FACULTY, UserRole.RESEARCH_COORDINATOR}),
        body={
            "title": "Matrix",
            "description": "Matrix",
            "opportunity_type": "research_assistant",
            "project_id": "00000000-0000-0000-0000-000000000001",
            "positions": 1,
            "deadline": "2099-01-01",
        },
        allowed_status=404,
    ),
    Endpoint(
        "POST",
        "/api/v1/opportunities/{id}/applications",
        frozenset({UserRole.STUDENT, UserRole.FACULTY, UserRole.RESEARCH_COORDINATOR}),
        needs_target=True,
        body={"statement": "Matrix"},
        allowed_status=404,
    ),
    Endpoint("GET", "/api/v1/me/applications", frozenset(ALL_ROLES)),
    # Step 8: collaboration requests. Admins can't send; the random recipient
    # doesn't exist, so allowed senders get 404.
    Endpoint(
        "POST",
        "/api/v1/collaborations",
        frozenset({UserRole.STUDENT, UserRole.FACULTY, UserRole.RESEARCH_COORDINATOR}),
        body={"recipient_id": "00000000-0000-0000-0000-000000000001", "message": "Matrix"},
        allowed_status=404,
    ),
    Endpoint("GET", "/api/v1/me/collaborations", frozenset(ALL_ROLES)),
    # Step 9: recommendations are personal to the caller; every role gets
    # their own (an admin's collaborator list is simply empty).
    Endpoint("GET", "/api/v1/recommendations", frozenset(ALL_ROLES)),
    # Step 10: saved items and dashboards are personal; reports are open to
    # everyone but only moderators see the queue.
    Endpoint("GET", "/api/v1/me/saved", frozenset(ALL_ROLES)),
    Endpoint(
        "POST",
        "/api/v1/me/saved",
        frozenset(ALL_ROLES),
        body={"project_id": "00000000-0000-0000-0000-000000000001"},
        allowed_status=404,
    ),
    Endpoint("GET", "/api/v1/me/dashboard", frozenset(ALL_ROLES)),
    Endpoint(
        "POST",
        "/api/v1/reports",
        frozenset(ALL_ROLES),
        body={
            "target_type": "project",
            "target_id": "00000000-0000-0000-0000-000000000001",
            "reason": "This looks like spam to me.",
        },
        allowed_status=404,
    ),
    Endpoint("GET", "/api/v1/admin/reports", COORDINATOR_AND_ADMIN),
    # Step 11: the facility catalogue is public to signed-in users; managing
    # it needs facility:manage, approving bookings needs booking:approve.
    Endpoint("GET", "/api/v1/facilities", frozenset(ALL_ROLES)),
    Endpoint("GET", "/api/v1/equipment", frozenset(ALL_ROLES)),
    # Admin only here: a coordinator holds facility:manage but must create
    # inside the department they oversee, and this generic fixture's
    # coordinator has no scope -- so they legitimately get 403 too. The
    # scoped coordinator path is covered in tests/test_facilities.py.
    Endpoint(
        "POST",
        "/api/v1/facilities",
        frozenset({UserRole.ADMIN}),
        body={"name": "Matrix Lab"},
        allowed_status=201,
    ),
    Endpoint(
        "POST",
        "/api/v1/bookings",
        frozenset(ALL_ROLES),
        body={
            "equipment_id": "00000000-0000-0000-0000-000000000001",
            "starts_at": "2099-01-01T09:00:00+00:00",
            "ends_at": "2099-01-01T10:00:00+00:00",
            "purpose": "Matrix",
        },
        allowed_status=404,
    ),
    Endpoint("GET", "/api/v1/me/bookings", frozenset(ALL_ROLES)),
    Endpoint("GET", "/api/v1/coordinator/booking-queue", COORDINATOR_AND_ADMIN),
    # Step 12: funding is public to signed-in users, managed by coordinator
    # and admin; notifications are strictly personal.
    Endpoint("GET", "/api/v1/funding", frozenset(ALL_ROLES)),
    Endpoint(
        "POST",
        "/api/v1/funding",
        COORDINATOR_AND_ADMIN,
        body={
            "organization": "Matrix Council",
            "title": "Matrix demo call",
            "description": "Matrix demo call description.",
            "deadline": "2099-01-01",
        },
        allowed_status=201,
    ),
    Endpoint("GET", "/api/v1/me/notifications", frozenset(ALL_ROLES)),
    Endpoint(
        "POST",
        "/api/v1/me/notifications/read-all",
        frozenset(ALL_ROLES),
        body={},
    ),
    # Provisioning accounts (ADR 0019). Everyone above student holds
    # user:create; what they may create is decided by their own role, and the
    # body carries no role at all. The generic fixture's users have no
    # department, so an authorised caller falls through to a scope failure --
    # the point of the row is that a *student* is stopped before any of that.
    # The full matrix lives in tests/test_account_creation.py.
    Endpoint(
        "POST",
        "/api/v1/users",
        frozenset({UserRole.ADMIN}),
        body={
            "registration_number": "MATRIX0001",
            "full_name": "Matrix Person",
        },
        # An admin appoints a coordinator and must say which department they
        # will oversee; the fixture names none, so this is the 422 that says
        # "authorised, but incomplete" rather than "not allowed".
        allowed_status=422,
    ),
    # Step 14: analytics and the collaboration network are for coordinators
    # and admins; platform settings are admin-only.
    Endpoint("GET", "/api/v1/analytics/overview", COORDINATOR_AND_ADMIN),
    Endpoint("GET", "/api/v1/analytics/network", COORDINATOR_AND_ADMIN),
    Endpoint("GET", "/api/v1/admin/settings", frozenset({UserRole.ADMIN})),
    # Students must not be able to browse other students.
    Endpoint(
        "GET",
        "/api/v1/students",
        frozenset({UserRole.FACULTY, UserRole.RESEARCH_COORDINATOR, UserRole.ADMIN}),
    ),
)


@dataclass(frozen=True, slots=True)
class AuthzCase:
    endpoint: Endpoint
    role: UserRole | None  # None = anonymous
    expected_status: int


def _build_cases() -> list[AuthzCase]:
    cases: list[AuthzCase] = []
    for endpoint in ENDPOINTS:
        cases.append(AuthzCase(endpoint, None, 401))
        for role in ALL_ROLES:
            expected = endpoint.allowed_status if role in endpoint.allowed_roles else 403
            cases.append(AuthzCase(endpoint, role, expected))
    return cases


AUTHZ_CASES = _build_cases()


def _case_id(case: AuthzCase) -> str:
    role_label = case.role.value if case.role is not None else "anonymous"
    endpoint = case.endpoint
    return f"{endpoint.method}_{endpoint.path_template}_as_{role_label}_{case.expected_status}"


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        yield test_client


@pytest.mark.parametrize("case", AUTHZ_CASES, ids=_case_id)
def test_authorization_matrix(
    case: AuthzCase, client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    headers: dict[str, str] = {}
    if case.role is not None:
        actor = seed_user(case.role)
        headers = {"Authorization": f"Bearer {actor.access_token}"}

    path = case.endpoint.path_template
    if case.endpoint.needs_target:
        target = seed_user(UserRole.STUDENT)
        path = path.replace("{id}", str(target.id))

    response = client.request(case.endpoint.method, path, headers=headers, json=case.endpoint.body)

    assert response.status_code == case.expected_status
