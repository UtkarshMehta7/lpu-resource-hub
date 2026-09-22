"""Project workflow and visibility rules.

TRANSITIONS is the one place the project workflow is defined (per the
project's "one table per workflow" rule): the service looks every status
change up here and refuses anything that isn't listed.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import ColumnElement, or_, select, true

from app.modules.projects.models import Project, ProjectMember, ProjectStatus
from app.modules.users.models import CoordinatorScopeType, User, UserRole

Actor = Literal["owner", "reviewer", "admin"]

TRANSITIONS: dict[tuple[ProjectStatus, ProjectStatus], frozenset[Actor]] = {
    (ProjectStatus.DRAFT, ProjectStatus.PENDING_REVIEW): frozenset({"owner"}),
    (ProjectStatus.PENDING_REVIEW, ProjectStatus.ACTIVE): frozenset({"reviewer"}),
    (ProjectStatus.PENDING_REVIEW, ProjectStatus.DRAFT): frozenset({"reviewer"}),
    (ProjectStatus.ACTIVE, ProjectStatus.COMPLETED): frozenset({"owner"}),
    (ProjectStatus.ACTIVE, ProjectStatus.ARCHIVED): frozenset({"owner", "admin"}),
    # Admin moderation: anything not already archived can be archived.
    (ProjectStatus.DRAFT, ProjectStatus.ARCHIVED): frozenset({"admin"}),
    (ProjectStatus.PENDING_REVIEW, ProjectStatus.ARCHIVED): frozenset({"admin"}),
    (ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED): frozenset({"admin"}),
}

# Everyone signed in can see these; everything else is private to its owner,
# its members, the department's coordinator and admins.
PUBLIC_STATUSES = (ProjectStatus.ACTIVE, ProjectStatus.COMPLETED)

# The owner can edit while drafting and while the project is running, but
# not while it is under review (reviewers must see what they approve).
EDITABLE_STATUSES = frozenset({ProjectStatus.DRAFT, ProjectStatus.ACTIVE})


class InvalidTransitionError(Exception):
    """The requested status change isn't in TRANSITIONS for this actor."""


class NotOwnerError(Exception):
    """The caller can see the project but isn't its owner."""


class SelfReviewError(Exception):
    """A reviewer tried to review their own project."""


def assert_transition(current: ProjectStatus, target: ProjectStatus, actor: Actor) -> None:
    if actor not in TRANSITIONS.get((current, target), frozenset()):
        raise InvalidTransitionError


def assert_owner(user: User, project: Project) -> None:
    if project.owner_id != user.id:
        raise NotOwnerError


def assert_not_own_project(reviewer: User, project: Project) -> None:
    if project.owner_id == reviewer.id:
        raise SelfReviewError


def visibility_filter(viewer: User) -> ColumnElement[bool]:
    """Rows the viewer may know exist. Applied in every query, so hidden
    projects never leave the database; a hidden project is a 404."""
    if viewer.role is UserRole.ADMIN:
        return true()

    conditions: list[ColumnElement[bool]] = [
        Project.status.in_(PUBLIC_STATUSES),
        Project.owner_id == viewer.id,
        Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id == viewer.id)),
    ]
    if (
        viewer.role is UserRole.RESEARCH_COORDINATOR
        and viewer.coordinator_scope_type is CoordinatorScopeType.DEPARTMENT
        and viewer.coordinator_scope_id is not None
    ):
        conditions.append(Project.department_id == viewer.coordinator_scope_id)
    return or_(*conditions)
