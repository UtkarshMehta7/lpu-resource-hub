"""Resource policy for researcher verification: scope + self-verify guards.

Checked after the target user/profile is loaded, per docs/architecture.md
§6's resource-policy layer -- the first real usage of "coordinator scope"
now that departments exist (Step 2 only had the columns).
"""

from __future__ import annotations

from app.modules.users.models import CoordinatorScopeType, User, UserRole


class SelfVerificationError(Exception):
    """Raised when a reviewer tries to verify their own profile."""


class OutOfScopeError(Exception):
    """Raised when a coordinator tries to verify a researcher outside their department."""


def assert_not_self_verification(reviewer: User, target: User) -> None:
    if reviewer.id == target.id:
        raise SelfVerificationError


def assert_in_coordinator_scope(reviewer: User, target: User) -> None:
    """No-op for ADMIN (unrestricted). A RESEARCH_COORDINATOR must have a
    DEPARTMENT scope matching the target's department."""
    if reviewer.role is not UserRole.RESEARCH_COORDINATOR:
        return
    in_scope = (
        reviewer.coordinator_scope_type is CoordinatorScopeType.DEPARTMENT
        and reviewer.coordinator_scope_id is not None
        and reviewer.coordinator_scope_id == target.department_id
    )
    if not in_scope:
        raise OutOfScopeError
