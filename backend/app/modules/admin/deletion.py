"""Removing an account, down the same hierarchy that creates one.

Deactivation and deletion answer different questions. Deactivation is "this
person has left": the account stops working, the history stays intact and
attributable. Deletion is "this account should never have existed": a typo in
a registration number, a duplicate, a test account. It takes the row away for
good.

Deleting a person who has actually used the platform takes their work with
them -- the database cascades to their projects, opportunities, publications,
applications, bookings and collaboration requests. That is occasionally what
somebody means, and never what they should discover afterwards, so every
deletion is costed first (`deletion_impact`) and the caller is shown what
goes. What survives is anything recording a *decision* they made about
somebody else -- verifications, reviews, approvals, audit entries -- which is
set to NULL rather than deleted, because the decision still happened.

Who may remove whom is `DELETABLE_ROLES` in app/core/permissions.py, plus the
same department scope that governs who may create whom.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass

from sqlalchemy import false as sa_false
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.pagination import PageParams
from app.core.permissions import deletable_roles, may_delete_role
from app.db.base import Base
from app.modules.applications.models import Application
from app.modules.audit import service as audit_service
from app.modules.bookings.models import Booking
from app.modules.collaborations.models import CollaborationRequest
from app.modules.messages.models import Message
from app.modules.opportunities.models import Opportunity
from app.modules.profiles.models import ResearcherProfile, VerificationStatus
from app.modules.projects.models import Project, ProjectMember
from app.modules.publications.models import Publication
from app.modules.reports.models import ContentReport
from app.modules.users.models import CoordinatorScopeType, User, UserRole


class NotAllowedRoleError(Exception):
    """This role may not delete accounts of the target's role."""


class OutOfScopeError(Exception):
    """The target is outside the department this actor is responsible for."""


class NoDepartmentError(Exception):
    """The actor has no department, so no scope to act within."""


class NotVerifiedError(Exception):
    """An unverified faculty member has not yet been vouched for."""


class SelfDeletionError(Exception):
    """Nobody deletes their own account."""


@dataclass(frozen=True, slots=True)
class DeletionImpact:
    """What disappears along with the account.

    Counts, not a list: this exists so a person can weigh the decision, and
    an admin clearing out demo accounts should not have to read 80 titles.

    Only what somebody would miss. The cascade also removes the account's own
    notifications, saved items, skills, research areas, profile and sessions;
    those are the account, not work lost with it, and listing them would bury
    the two lines that matter.
    """

    projects_owned: int
    project_memberships: int
    opportunities_created: int
    publications_created: int
    applications_submitted: int
    collaboration_requests: int
    bookings: int
    reports_filed: int
    messages_sent: int
    accounts_provisioned: int

    @property
    def destroys_content(self) -> bool:
        """True when deleting takes more than the account itself."""
        return any(
            count > 0
            for field, count in asdict(self).items()
            # Accounts they provisioned are NOT deleted -- those rows keep
            # working, they simply stop naming a creator.
            if field != "accounts_provisioned"
        )


def _count(db: Session, model: type[Base], *criteria: ColumnElement[bool]) -> int:
    statement = select(func.count()).select_from(model).where(*criteria)
    return db.execute(statement).scalar_one()


def deletion_impact(db: Session, target: User) -> DeletionImpact:
    """Count what a deletion would take with it. Reads only."""
    return DeletionImpact(
        projects_owned=_count(db, Project, Project.owner_id == target.id),
        project_memberships=_count(db, ProjectMember, ProjectMember.user_id == target.id),
        opportunities_created=_count(db, Opportunity, Opportunity.created_by == target.id),
        publications_created=_count(db, Publication, Publication.created_by == target.id),
        applications_submitted=_count(db, Application, Application.applicant_id == target.id),
        collaboration_requests=_count(
            db,
            CollaborationRequest,
            or_(
                CollaborationRequest.sender_id == target.id,
                CollaborationRequest.recipient_id == target.id,
            ),
        ),
        bookings=_count(db, Booking, Booking.user_id == target.id),
        reports_filed=_count(db, ContentReport, ContentReport.reporter_id == target.id),
        # Their half of every thread goes with them. Counted so the
        # confirmation says so rather than the other party finding out.
        messages_sent=_count(db, Message, Message.sender_id == target.id),
        accounts_provisioned=_count(db, User, User.created_by == target.id),
    )


def _actor_department(actor: User) -> uuid.UUID | None:
    """The department this actor answers for.

    A coordinator's authority is the scope an admin gave them, not the
    department they happen to work in -- the same rule provisioning uses.
    """
    if actor.role is UserRole.RESEARCH_COORDINATOR:
        if (
            actor.coordinator_scope_type is CoordinatorScopeType.DEPARTMENT
            and actor.coordinator_scope_id is not None
        ):
            return actor.coordinator_scope_id
        return None
    return actor.department_id


def assert_may_delete(db: Session, actor: User, target: User) -> None:
    """Raise unless `actor` may delete `target`. No writes.

    Kept separate from the deletion itself so the impact endpoint can answer
    with exactly the same authority check, rather than a second copy of it
    that could drift.
    """
    if actor.id == target.id:
        # Even an administrator: there would be nobody left to undo it, and
        # stepping down is the deliberate way to give up the role.
        #
        # This is also what keeps the platform administrable. Only an
        # administrator may delete an administrator, so the last one can only
        # ever be deleted by themselves -- and that is exactly what this
        # refuses. No separate "last administrator" check is reachable.
        raise SelfDeletionError

    if not may_delete_role(actor.role, target.role):
        raise NotAllowedRoleError

    if actor.role is UserRole.ADMIN:
        # An administrator answers for the whole platform, so no scope applies.
        return

    if actor.role is UserRole.FACULTY:
        # The same rule as creating: a self-declared department is not
        # authority until a coordinator has verified the claim.
        profile = db.get(ResearcherProfile, actor.id)
        if profile is None or profile.verification_status is not VerificationStatus.VERIFIED:
            raise NotVerifiedError

    scope = _actor_department(actor)
    if scope is None:
        raise NoDepartmentError
    if target.department_id != scope:
        raise OutOfScopeError


def delete_account(db: Session, actor: User, target: User, *, ip: str | None) -> DeletionImpact:
    """Delete `target` and everything the database cascades from it.

    Returns what was destroyed, which is also what the audit entry records:
    the row is gone afterwards, so the log has to carry enough to say who was
    removed -- the id alone would point at nothing.
    """
    assert_may_delete(db, actor, target)
    impact = deletion_impact(db, target)

    audit_service.record(
        db,
        actor_id=actor.id,
        action="user.deleted",
        entity_type="user",
        entity_id=target.id,
        before={
            "registration_number": target.registration_number,
            "full_name": target.full_name,
            "role": target.role.value,
            "department_id": str(target.department_id) if target.department_id else None,
            "is_active": target.is_active,
            **asdict(impact),
        },
        ip=ip,
    )
    db.delete(target)
    db.commit()
    return impact


def list_manageable(db: Session, actor: User, params: PageParams) -> tuple[list[User], int]:
    """The people this actor is responsible for: those they may remove.

    The list and the buttons on it come from the same rule, so a row can only
    appear here if the deletion would actually be permitted -- which is the
    difference between a usable page and one that hands out 403s.

    A student, and a coordinator or faculty member with no scope, sees an
    empty list rather than an error: there is genuinely nobody, and that is
    information, not a failure.
    """
    roles = deletable_roles(actor.role)
    query = select(User).where(User.id != actor.id)
    if not roles:
        query = query.where(sa_false())
    else:
        query = query.where(User.role.in_(roles))
        if actor.role is not UserRole.ADMIN:
            scope = _actor_department(actor)
            if scope is None:
                query = query.where(sa_false())
            else:
                query = query.where(User.department_id == scope)

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = (
        db.execute(query.order_by(User.full_name).offset(params.offset).limit(params.page_size))
        .scalars()
        .all()
    )
    # Rows and the total, not a Page: the page model is a Pydantic one, and
    # which response schema wraps these is the router's business.
    return list(rows), total
