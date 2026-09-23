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
    USER_CREATE = "user:create"
    USER_LIST = "user:list"
    USER_UPDATE = "user:update"
    USER_UPDATE_ROLE = "user:update_role"
    USER_ACTIVATE = "user:activate"
    USER_DEACTIVATE = "user:deactivate"
    USER_DELETE = "user:delete"
    AUDIT_READ = "audit:read"
    SCHOOL_MANAGE = "school:manage"
    DEPARTMENT_MANAGE = "department:manage"
    TAXONOMY_MANAGE = "taxonomy:manage"
    PROFILE_VERIFY = "profile:verify"
    STUDENT_DISCOVER = "student:discover"
    PROJECT_CREATE = "project:create"
    PROJECT_REVIEW = "project:review"
    PUBLICATION_CREATE = "publication:create"
    OPPORTUNITY_CREATE = "opportunity:create"
    APPLICATION_SUBMIT = "application:submit"
    COLLABORATION_SEND = "collaboration:send"
    REPORT_MODERATE = "report:moderate"
    ANALYTICS_READ = "analytics:read"
    FACILITY_MANAGE = "facility:manage"
    BOOKING_APPROVE = "booking:approve"
    FUNDING_MANAGE = "funding:manage"


# A role inherits everything its parent can do. ADMIN's powers are listed
# explicitly (operational/moderation), not "inherits everyone".
ROLE_HIERARCHY: dict[UserRole, UserRole | None] = {
    UserRole.STUDENT: None,
    UserRole.FACULTY: None,
    UserRole.RESEARCH_COORDINATOR: UserRole.FACULTY,
    UserRole.ADMIN: None,
}

_OWN_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.STUDENT: frozenset({Permission.APPLICATION_SUBMIT, Permission.COLLABORATION_SEND}),
    # First FACULTY-level grant: RESEARCH_COORDINATOR inherits it for free.
    UserRole.FACULTY: frozenset(
        {
            Permission.STUDENT_DISCOVER,
            # Faculty create student accounts for their own department; the
            # department limit is a resource policy, not a permission.
            Permission.USER_CREATE,
            # ...and may remove the same accounts again. Which roles, and
            # whose, is DELETABLE_ROLES plus a scope check, not a permission.
            Permission.USER_DELETE,
            Permission.PROJECT_CREATE,
            Permission.PUBLICATION_CREATE,
            Permission.OPPORTUNITY_CREATE,
            # Faculty apply only to COLLABORATION openings (checked in the service).
            Permission.APPLICATION_SUBMIT,
            Permission.COLLABORATION_SEND,
        }
    ),
    UserRole.RESEARCH_COORDINATOR: frozenset(
        {
            Permission.TAXONOMY_MANAGE,
            Permission.PROFILE_VERIFY,
            Permission.PROJECT_REVIEW,
            Permission.REPORT_MODERATE,
            Permission.ANALYTICS_READ,
            Permission.FACILITY_MANAGE,
            Permission.BOOKING_APPROVE,
            Permission.FUNDING_MANAGE,
        }
    ),
    UserRole.ADMIN: frozenset(
        {
            Permission.USER_CREATE,
            Permission.USER_LIST,
            Permission.USER_UPDATE,
            Permission.USER_UPDATE_ROLE,
            Permission.USER_ACTIVATE,
            Permission.USER_DEACTIVATE,
            Permission.USER_DELETE,
            Permission.AUDIT_READ,
            Permission.SCHOOL_MANAGE,
            Permission.DEPARTMENT_MANAGE,
            Permission.TAXONOMY_MANAGE,
            Permission.PROFILE_VERIFY,
            Permission.STUDENT_DISCOVER,
            Permission.PROJECT_REVIEW,
            Permission.REPORT_MODERATE,
            Permission.ANALYTICS_READ,
            Permission.FACILITY_MANAGE,
            Permission.BOOKING_APPROVE,
            Permission.FUNDING_MANAGE,
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


# Accounts are provisioned down the institutional hierarchy, one rung at a
# time: an admin appoints coordinators, a coordinator appoints the faculty of
# their department, a faculty member enrols their students. Nobody creates a
# peer, nobody creates upwards, and students create nobody.
#
# This table is the single authority on it. The role of a new account is
# *derived* from its creator and never read from the request, so there is no
# client-supplied role to validate -- or to forge.
CREATABLE_ROLE: dict[UserRole, UserRole | None] = {
    UserRole.ADMIN: UserRole.RESEARCH_COORDINATOR,
    UserRole.RESEARCH_COORDINATOR: UserRole.FACULTY,
    UserRole.FACULTY: UserRole.STUDENT,
    UserRole.STUDENT: None,
}


def creatable_role(creator_role: UserRole) -> UserRole | None:
    """The one role this role may bring into the platform, or None."""
    return CREATABLE_ROLE[creator_role]


# Removal runs down the same hierarchy, but unlike creation it is not limited
# to a single rung: an administrator answers for the whole platform, so they
# may remove anyone, while everybody else may only remove people below them.
# Students remove nobody.
#
# This decides the *role*. Whose account, in which department, is a separate
# scope check (see app/modules/admin/deletion.py) -- a coordinator may delete
# faculty, but not another department's faculty.
DELETABLE_ROLES: dict[UserRole, frozenset[UserRole]] = {
    UserRole.ADMIN: frozenset(
        {UserRole.STUDENT, UserRole.FACULTY, UserRole.RESEARCH_COORDINATOR, UserRole.ADMIN}
    ),
    UserRole.RESEARCH_COORDINATOR: frozenset({UserRole.STUDENT, UserRole.FACULTY}),
    UserRole.FACULTY: frozenset({UserRole.STUDENT}),
    UserRole.STUDENT: frozenset(),
}


def deletable_roles(actor_role: UserRole) -> frozenset[UserRole]:
    """The roles this role may remove from the platform."""
    return DELETABLE_ROLES[actor_role]


def may_delete_role(actor_role: UserRole, target_role: UserRole) -> bool:
    return target_role in DELETABLE_ROLES[actor_role]


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
