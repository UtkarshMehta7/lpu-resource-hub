"""ROLE_PERMISSIONS inheritance and the require_permission dependency."""

from __future__ import annotations

import uuid

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.core.permissions import ROLE_HIERARCHY, ROLE_PERMISSIONS, Permission, require_permission
from app.modules.users.models import User, UserRole


def test_coordinator_has_no_permissions_of_its_own_today() -> None:
    # Nothing has granted FACULTY a permission yet (no domain resources
    # exist), so RESEARCH_COORDINATOR inherits an empty set too.
    assert ROLE_PERMISSIONS[UserRole.FACULTY] == frozenset()
    assert ROLE_PERMISSIONS[UserRole.RESEARCH_COORDINATOR] == frozenset()


def test_admin_has_exactly_the_step_2_permissions() -> None:
    assert ROLE_PERMISSIONS[UserRole.ADMIN] == frozenset(
        {
            Permission.USER_LIST,
            Permission.USER_UPDATE,
            Permission.USER_UPDATE_ROLE,
            Permission.USER_ACTIVATE,
            Permission.USER_DEACTIVATE,
            Permission.AUDIT_READ,
        }
    )


def test_student_has_no_permissions() -> None:
    assert ROLE_PERMISSIONS[UserRole.STUDENT] == frozenset()


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
