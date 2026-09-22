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


@dataclass(frozen=True, slots=True)
class Endpoint:
    method: str
    path_template: str  # "{id}" is replaced with a freshly seeded student's id
    allowed_roles: frozenset[UserRole]
    needs_target: bool = False
    body: dict[str, object] | None = None


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
            expected = 200 if role in endpoint.allowed_roles else 403
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
