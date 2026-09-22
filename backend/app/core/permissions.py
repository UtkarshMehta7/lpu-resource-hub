"""Role -> permission map and the `require_permission` dependency.

Only permissions actually enforced by a built module belong here (see
docs/rbac-matrix.md for the full forward-looking design). A permission is a
"resource:action" string. `ROLE_PERMISSIONS` is derived from `ROLE_HIERARCHY`
so that granting FACULTY a permission automatically extends it to
RESEARCH_COORDINATOR without editing this file again.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.core.deps import get_current_user
from app.modules.users.models import User, UserRole


class Permission(StrEnum):
    USER_LIST = "user:list"
    USER_UPDATE = "user:update"
    USER_UPDATE_ROLE = "user:update_role"
    USER_ACTIVATE = "user:activate"
    USER_DEACTIVATE = "user:deactivate"
    AUDIT_READ = "audit:read"
    SCHOOL_MANAGE = "school:manage"
    DEPARTMENT_MANAGE = "department:manage"
    TAXONOMY_MANAGE = "taxonomy:manage"
    PROFILE_VERIFY = "profile:verify"
    STUDENT_DISCOVER = "student:discover"


# A role inherits everything its parent can do. ADMIN's powers are listed
# explicitly (operational/moderation), not "inherits everyone".
ROLE_HIERARCHY: dict[UserRole, UserRole | None] = {
    UserRole.STUDENT: None,
    UserRole.FACULTY: None,
    UserRole.RESEARCH_COORDINATOR: UserRole.FACULTY,
    UserRole.ADMIN: None,
}

_OWN_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.STUDENT: frozenset(),
    # First FACULTY-level grant: RESEARCH_COORDINATOR inherits it for free.
    UserRole.FACULTY: frozenset({Permission.STUDENT_DISCOVER}),
    UserRole.RESEARCH_COORDINATOR: frozenset(
        {
            Permission.TAXONOMY_MANAGE,
            Permission.PROFILE_VERIFY,
        }
    ),
    UserRole.ADMIN: frozenset(
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
        }
    ),
}


def _effective_permissions(role: UserRole) -> frozenset[Permission]:
    permissions = set(_OWN_PERMISSIONS[role])
    parent = ROLE_HIERARCHY[role]
    if parent is not None:
        permissions |= _effective_permissions(parent)
    return frozenset(permissions)


ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    role: _effective_permissions(role) for role in UserRole
}


def require_permission(permission: Permission) -> Callable[..., User]:
    """FastAPI dependency factory: 401 if unauthenticated, 403 if lacking `permission`."""

    def dependency(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if permission not in ROLE_PERMISSIONS[current_user.role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return dependency
