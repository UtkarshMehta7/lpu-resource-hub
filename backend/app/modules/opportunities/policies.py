"""Opportunity workflow and visibility rules.

TRANSITIONS is the one place the opportunity workflow is defined. "system"
is the service itself: an opportunity becomes FILLED when its last position
is accepted, never by a direct request.
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import ColumnElement, or_, true

from app.modules.opportunities.models import Opportunity, OpportunityStatus
from app.modules.users.models import CoordinatorScopeType, User, UserRole

Actor = Literal["owner", "coordinator", "admin", "system"]

TRANSITIONS: dict[tuple[OpportunityStatus, OpportunityStatus], frozenset[Actor]] = {
    (OpportunityStatus.DRAFT, OpportunityStatus.OPEN): frozenset({"owner"}),
    (OpportunityStatus.DRAFT, OpportunityStatus.CLOSED): frozenset({"owner", "admin"}),
    (OpportunityStatus.OPEN, OpportunityStatus.CLOSED): frozenset(
        {"owner", "coordinator", "admin"}
    ),
    (OpportunityStatus.OPEN, OpportunityStatus.FILLED): frozenset({"system"}),
}

# The owner can edit while drafting and while it's open.
EDITABLE_STATUSES = frozenset({OpportunityStatus.DRAFT, OpportunityStatus.OPEN})


class InvalidTransitionError(Exception):
    """The requested status change isn't in TRANSITIONS for this actor."""


class NotOwnerError(Exception):
    """The caller can see the opportunity but didn't create it."""


def assert_transition(current: OpportunityStatus, target: OpportunityStatus, actor: Actor) -> None:
    if actor not in TRANSITIONS.get((current, target), frozenset()):
        raise InvalidTransitionError


def coordinator_department(user: User) -> uuid.UUID | None:
    """The department a coordinator oversees, if their scope is a department."""
    if (
        user.role is UserRole.RESEARCH_COORDINATOR
        and user.coordinator_scope_type is CoordinatorScopeType.DEPARTMENT
    ):
        return user.coordinator_scope_id
    return None


def actor_for(user: User, opportunity: Opportunity) -> Actor | None:
    """How `user` relates to `opportunity` for workflow purposes."""
    if opportunity.created_by == user.id:
        return "owner"
    if user.role is UserRole.ADMIN:
        return "admin"
    scope = coordinator_department(user)
    if scope is not None and scope == opportunity.department_id:
        return "coordinator"
    return None


def visibility_filter(viewer: User) -> ColumnElement[bool]:
    """Drafts are private to their creator, the scoped coordinator and admins;
    everything else is visible to every signed-in user."""
    if viewer.role is UserRole.ADMIN:
        return true()
    conditions: list[ColumnElement[bool]] = [
        Opportunity.status != OpportunityStatus.DRAFT,
        Opportunity.created_by == viewer.id,
    ]
    scope = coordinator_department(viewer)
    if scope is not None:
        conditions.append(Opportunity.department_id == scope)
    return or_(*conditions)
