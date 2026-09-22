"""ROLE_PERMISSIONS inheritance and the require_permission dependency."""

from __future__ import annotations

import uuid

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.core.permissions import ROLE_HIERARCHY, ROLE_PERMISSIONS, Permission, require_permission
from app.modules.users.models import User, UserRole


def test_faculty_has_exactly_its_own_grants() -> None:
    assert ROLE_PERMISSIONS[UserRole.FACULTY] == frozenset(
        {
            Permission.STUDENT_DISCOVER,
            Permission.PROJECT_CREATE,
            Permission.PUBLICATION_CREATE,
            Permission.OPPORTUNITY_CREATE,
            Permission.APPLICATION_SUBMIT,
        }
    )


def test_coordinator_inherits_faculty_grants_on_top_of_its_own() -> None:
    """Step 4 gave FACULTY its first permission, so this now exercises the
    inheritance mechanism with real data rather than a hypothetical."""
    assert ROLE_PERMISSIONS[UserRole.RESEARCH_COORDINATOR] == frozenset(
        {
            Permission.TAXONOMY_MANAGE,
            Permission.PROFILE_VERIFY,
            Permission.PROJECT_REVIEW,
            Permission.STUDENT_DISCOVER,  # inherited from FACULTY
            Permission.PROJECT_CREATE,  # inherited from FACULTY
            Permission.PUBLICATION_CREATE,  # inherited from FACULTY
            Permission.OPPORTUNITY_CREATE,  # inherited from FACULTY
            Permission.APPLICATION_SUBMIT,  # inherited from FACULTY
        }
    )


def test_admin_has_exactly_its_own_grants() -> None:
    assert ROLE_PERMISSIONS[UserRole.ADMIN] == frozenset(
        {
            Permission.USER_LIST,
            Permission.USER_UPDATE,
            Permission.USER_UPDATE_ROLE,
            Permission.USER_ACTIVATE,
            Permission.USER_DEACTIVATE,
            Permission.AUDIT_READ,
            Permission.SCHOOL_MANAGE,
            Permission.DEPARTMENT_MANAGE,
            Permission.TAXONOMY_MANAGE,
            Permission.PROFILE_VERIFY,
            Permission.STUDENT_DISCOVER,
            Permission.PROJECT_REVIEW,
        }
    )


def test_student_can_only_apply() -> None:
    assert ROLE_PERMISSIONS[UserRole.STUDENT] == frozenset({Permission.APPLICATION_SUBMIT})


def test_coordinator_inherits_a_hypothetical_faculty_permission() -> None:
    """Proves the inheritance mechanism itself, independent of what's granted today."""
    assert ROLE_HIERARCHY[UserRole.RESEARCH_COORDINATOR] is UserRole.FACULTY

    fake_permission = "project:create"
    own_permissions = {
        UserRole.STUDENT: frozenset(),
        UserRole.FACULTY: frozenset({fake_permission}),
        UserRole.RESEARCH_COORDINATOR: frozenset(),
        UserRole.ADMIN: frozenset(),
    }

    def effective_for(role: UserRole) -> frozenset[str]:
        permissions = set(own_permissions[role])
        parent = ROLE_HIERARCHY[role]
        if parent is not None:
            permissions |= effective_for(parent)
        return frozenset(permissions)

    assert fake_permission in effective_for(UserRole.RESEARCH_COORDINATOR)
    assert fake_permission not in effective_for(UserRole.STUDENT)
    assert fake_permission not in effective_for(UserRole.ADMIN)


def _build_protected_app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(require_permission(Permission.AUDIT_READ))])
    def protected() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_require_permission_401_when_unauthenticated() -> None:
    app = _build_protected_app()

    def _raise_unauthenticated() -> None:
        raise HTTPException(status_code=401, detail="Could not validate credentials.")

    app.dependency_overrides[get_current_user] = _raise_unauthenticated

    response = TestClient(app).get("/protected")

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("role", "expected_status"), [(UserRole.STUDENT, 403), (UserRole.ADMIN, 200)]
)
def test_require_permission_403_vs_200_by_role(role: UserRole, expected_status: int) -> None:
    app = _build_protected_app()
    fake_user = User(
        id=uuid.uuid4(),
        email="fake@example.com",
        password_hash="unused",
        full_name="Fake",
        role=role,
        is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: fake_user

    response = TestClient(app).get("/protected")

    assert response.status_code == expected_status
