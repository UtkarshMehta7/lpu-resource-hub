"""Project workflow and visibility rules.

TRANSITIONS is the one place the project workflow is defined (per the
project's "one table per workflow" rule): the service looks every status
change up here and refuses anything that isn't listed.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import ColumnElement, func, or_, select, true
from sqlalchemy.orm import Session

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
    if viewer.role is UserRole.DEAN_OF_RESEARCH:
        # A dean decides work that crosses departments, so they must be able
        # to SEE it while it is pending -- a reviewer who cannot open what
        # they are asked to approve is no reviewer. Whether a given project
        # actually crosses is a property of its team, which SQL here cannot
        # see; `may_review` makes that judgement on the loaded row. This
        # widens visibility, not authority: everything else a dean may do is
        # still read-only.
        conditions.append(true())
    return or_(*conditions)


def crosses_departments(db: Session, project: Project) -> bool:
    """Whether this project's team reaches outside its own department.

    A coordinator's authority stops at their department, so a project whose
    members sit in two of them has no reviewer who can see the whole team.
    That is the gap the Dean of Research fills, and it is computed rather than
    flagged so nobody has to remember to set it.
    """
    if project.department_id is None:
        # Belongs to no department, so no coordinator can reach it either.
        return True
    outside = db.execute(
        select(func.count())
        .select_from(ProjectMember)
        .join(User, User.id == ProjectMember.user_id)
        .where(
            ProjectMember.project_id == project.id,
            User.department_id.is_not(None),
            User.department_id != project.department_id,
        )
    ).scalar_one()
    return bool(outside)


def may_review(db: Session, reviewer: User, project: Project) -> bool:
    """Whether this person may decide this project.

    An admin reviews anything. A coordinator reviews their own department's
    work. A dean reviews what crosses departments -- and nothing else, because
    a dean deciding ordinary departmental work would quietly replace the
    coordinator who is meant to.
    """
    if reviewer.role is UserRole.ADMIN:
        return True
    if reviewer.role is UserRole.DEAN_OF_RESEARCH:
        return crosses_departments(db, project)
    if reviewer.role is UserRole.RESEARCH_COORDINATOR:
        return (
            reviewer.coordinator_scope_type is CoordinatorScopeType.DEPARTMENT
            and reviewer.coordinator_scope_id is not None
            and reviewer.coordinator_scope_id == project.department_id
        )
    return False
