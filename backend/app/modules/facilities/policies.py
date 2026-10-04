"""Who may manage a facility or its equipment.

Admins manage anything. A research coordinator manages the facilities of the
department they oversee. A facility custodian manages the facilities assigned
to them, and no others. Anyone signed in can browse the catalogue.

`Permission.FACILITY_MANAGE` says a person may manage *a* facility; it never
says *every* facility. That difference is the point of the custodian role --
somebody looking after the Soil Lab has no business editing the Electron
Microscopy Suite, and holding the permission alone would let them.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, false, true

from app.modules.facilities.models import Facility
from app.modules.users.models import CoordinatorScopeType, User, UserRole


class OutOfScopeError(Exception):
    """Someone reached for a facility outside the scope they hold."""


def coordinator_department(user: User) -> uuid.UUID | None:
    if (
        user.role is UserRole.RESEARCH_COORDINATOR
        and user.coordinator_scope_type is CoordinatorScopeType.DEPARTMENT
    ):
        return user.coordinator_scope_id
    return None


def assert_can_manage(user: User, department_id: uuid.UUID | None) -> None:
    """Department-level scope, for creating a facility or managing by department."""
    if user.role is UserRole.ADMIN:
        return
    scope = coordinator_department(user)
    if scope is None or department_id is None or scope != department_id:
        raise OutOfScopeError


def may_manage_facility(user: User, facility: Facility) -> bool:
    """Whether this person may change this particular facility.

    Object-level, because a custodian's scope is a set of facilities rather
    than a department. Checked against the loaded row, so it cannot be
    satisfied by guessing an id.
    """
    if user.role is UserRole.ADMIN:
        return True
    if user.role is UserRole.FACILITY_CUSTODIAN:
        return facility.custodian_id == user.id
    if user.role is UserRole.RESEARCH_COORDINATOR:
        scope = coordinator_department(user)
        return scope is not None and facility.department_id == scope
    return False


def assert_may_manage_facility(user: User, facility: Facility) -> None:
    if not may_manage_facility(user, facility):
        raise OutOfScopeError


def manageable_facility_filter(user: User) -> ColumnElement[bool]:
    """Facilities this person may change, as a filter.

    Returned as a filter rather than a per-row test so a listing can never
    show something an action would then refuse.
    """
    if user.role is UserRole.ADMIN:
        return true()
    if user.role is UserRole.FACILITY_CUSTODIAN:
        return Facility.custodian_id == user.id
    scope = coordinator_department(user)
    if scope is not None:
        return Facility.department_id == scope
    return false()
