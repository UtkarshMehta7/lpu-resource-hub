"""Who may manage a facility or its equipment.

Admins manage anything; a research coordinator manages only facilities in
the department they oversee. Anyone signed in can browse the catalogue.
"""

from __future__ import annotations

import uuid

from app.modules.users.models import CoordinatorScopeType, User, UserRole


class OutOfScopeError(Exception):
    """A coordinator tried to manage a facility outside their department."""


def coordinator_department(user: User) -> uuid.UUID | None:
    if (
        user.role is UserRole.RESEARCH_COORDINATOR
        and user.coordinator_scope_type is CoordinatorScopeType.DEPARTMENT
    ):
        return user.coordinator_scope_id
    return None


def assert_can_manage(user: User, department_id: uuid.UUID | None) -> None:
    if user.role is UserRole.ADMIN:
        return
    scope = coordinator_department(user)
    if scope is None or department_id is None or scope != department_id:
        raise OutOfScopeError
