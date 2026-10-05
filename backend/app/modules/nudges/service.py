"""Nudging whoever has to act next.

Four things in this platform wait on somebody senior: a profile awaiting
verification, a project awaiting review, a booking awaiting approval, and an
application awaiting a decision. Until now the person waiting had no way to
say "this is still sitting there" except to find them in person.

Two rules keep a nudge from becoming a nuisance:

* **You may only nudge about your own thing**, and only while it is genuinely
  waiting. A nudge about somebody else's project, or about one that has
  already been decided, is refused.
* **One nudge per thing per day.** Enforced from the `nudges` table rather
  than trusted to the interface, because the interface is not what a
  determined person uses.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import INSTITUTION_WIDE_ROLES
from app.modules.applications.models import Application, ApplicationStatus
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.milestones.models import Milestone
from app.modules.milestones.risk import NEEDS_ATTENTION, RiskInput, assess
from app.modules.milestones.service import dependency_map
from app.modules.notifications.models import NotificationType
from app.modules.notifications.service import notify
from app.modules.nudges.models import Nudge, NudgeKind
from app.modules.opportunities.models import Opportunity
from app.modules.profiles.models import ResearcherProfile, VerificationStatus
from app.modules.projects.models import Project, ProjectStatus
from app.modules.users.models import CoordinatorScopeType, User, UserRole

#: How long before the same person may nudge about the same thing again.
COOLDOWN = timedelta(hours=24)


class NothingToNudgeAboutError(Exception):
    """The thing is not waiting on anyone, or is not the caller's to chase."""


class NudgeTooSoonError(Exception):
    """Already nudged about this recently."""

    def __init__(self, retry_after: datetime) -> None:
        super().__init__("nudged too recently")
        self.retry_after = retry_after


class NoRecipientError(Exception):
    """Nobody is in a position to act, so there is no one to tell."""


@dataclass(frozen=True, slots=True)
class NudgeResult:
    kind: NudgeKind
    recipients: int
    next_allowed_at: datetime


def _approvers(db: Session, department_id: uuid.UUID | None) -> list[User]:
    """Whoever can act on something in this department.

    The department's coordinators first; administrators are the fallback, and
    are included anyway when a department has no coordinator, so a nudge is
    never silently delivered to nobody.
    """
    coordinators: Sequence[User] = ()
    if department_id is not None:
        coordinators = db.scalars(
            select(User).where(
                User.role == UserRole.RESEARCH_COORDINATOR,
                User.is_active.is_(True),
                User.coordinator_scope_type == CoordinatorScopeType.DEPARTMENT,
                User.coordinator_scope_id == department_id,
            )
        ).all()
    if coordinators:
        return list(coordinators)
    return list(
        db.scalars(select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True))).all()
    )


def _profile_recipients(db: Session, actor: User, entity_id: uuid.UUID) -> tuple[list[User], str]:
    if entity_id != actor.id:
        raise NothingToNudgeAboutError
    profile = db.get(ResearcherProfile, actor.id)
    if profile is None or profile.verification_status is not VerificationStatus.PENDING:
        raise NothingToNudgeAboutError
    return _approvers(db, actor.department_id), "your profile verification"


def _project_recipients(db: Session, actor: User, entity_id: uuid.UUID) -> tuple[list[User], str]:
    project = db.get(Project, entity_id)
    if (
        project is None
        or project.deleted_at is not None
        or project.owner_id != actor.id
        or project.status is not ProjectStatus.PENDING_REVIEW
    ):
        raise NothingToNudgeAboutError
    return _approvers(db, project.department_id), f"the review of “{project.title}”"


def _booking_recipients(db: Session, actor: User, entity_id: uuid.UUID) -> tuple[list[User], str]:
    booking = db.get(Booking, entity_id)
    if (
        booking is None
        or booking.user_id != actor.id
        or booking.status is not BookingStatus.PENDING
    ):
        raise NothingToNudgeAboutError
    return _approvers(db, actor.department_id), "your equipment booking"


def _application_recipients(
    db: Session, actor: User, entity_id: uuid.UUID
) -> tuple[list[User], str]:
    application = db.get(Application, entity_id)
    if (
        application is None
        or application.applicant_id != actor.id
        or application.status is not ApplicationStatus.SUBMITTED
    ):
        raise NothingToNudgeAboutError
    opportunity = db.get(Opportunity, application.opportunity_id)
    if opportunity is None:
        raise NothingToNudgeAboutError
    owner = db.get(User, opportunity.created_by)
    if owner is None or not owner.is_active:
        raise NothingToNudgeAboutError
    return [owner], f"your application to “{opportunity.title}”"


def _at_risk_project_recipients(
    db: Session, actor: User, entity_id: uuid.UUID
) -> tuple[list[User], str]:
    """A dean asking a coordinator to look at a slipping project.

    The one nudge that is not about the sender's own work, so the ownership
    check every other resolver makes is replaced by two others:

    * the sender must be an institution-wide reader -- a coordinator would be
      nudging themselves, and a project owner already has PROJECT_REVIEW;
    * the project must actually be in trouble. "Please look at this" about a
      project that is perfectly on track is noise, and a reader who gets one
      such nudge discounts the next.

    Risk is derived on every read (ADR 0026), so it is asked for here rather
    than stored -- the same function the board and the project page use.
    """
    if actor.role not in INSTITUTION_WIDE_ROLES:
        raise NothingToNudgeAboutError
    project = db.get(Project, entity_id)
    if project is None or project.deleted_at is not None:
        raise NothingToNudgeAboutError
    if not _project_needs_attention(db, project.id):
        raise NothingToNudgeAboutError
    return _approvers(db, project.department_id), f"“{project.title}”, which is slipping"


def _project_needs_attention(db: Session, project_id: uuid.UUID) -> bool:
    """Whether any milestone on this project is overdue, at risk or blocked."""
    milestones = list(db.scalars(select(Milestone).where(Milestone.project_id == project_id)).all())
    if not milestones:
        return False
    dependencies = dependency_map(db, [m.id for m in milestones])
    by_id = {m.id: m for m in milestones}
    today = date.today()
    threshold = get_settings().milestone_at_risk_days
    for milestone in milestones:
        upstream = [
            RiskInput(status=by_id[d].status, due_date=by_id[d].due_date)
            for d in dependencies.get(milestone.id, [])
            if d in by_id
        ]
        risk = assess(
            RiskInput(status=milestone.status, due_date=milestone.due_date),
            today=today,
            threshold_days=threshold,
            depends_on=upstream,
        )
        if risk in NEEDS_ATTENTION:
            return True
    return False


_RESOLVERS = {
    NudgeKind.PROFILE_VERIFICATION: _profile_recipients,
    NudgeKind.PROJECT_REVIEW: _project_recipients,
    NudgeKind.BOOKING_APPROVAL: _booking_recipients,
    NudgeKind.APPLICATION_DECISION: _application_recipients,
    NudgeKind.PROJECT_AT_RISK: _at_risk_project_recipients,
}


def _last_nudge(db: Session, actor: User, kind: NudgeKind, entity_id: uuid.UUID) -> datetime | None:
    return db.scalar(
        select(func.max(Nudge.created_at)).where(
            Nudge.actor_id == actor.id, Nudge.kind == kind, Nudge.entity_id == entity_id
        )
    )


def send(db: Session, actor: User, kind: NudgeKind, entity_id: uuid.UUID) -> NudgeResult:
    """Tell whoever must act that somebody is waiting."""
    recipients, subject = _RESOLVERS[kind](db, actor, entity_id)
    if not recipients:
        raise NoRecipientError

    now = datetime.now(UTC)
    last = _last_nudge(db, actor, kind, entity_id)
    if last is not None and now - last < COOLDOWN:
        raise NudgeTooSoonError(last + COOLDOWN)

    for recipient in recipients:
        notify(
            db,
            user_id=recipient.id,
            notification_type=NotificationType.NUDGE_RECEIVED,
            payload={
                "kind": kind.value,
                "entity_id": str(entity_id),
                "subject": subject,
                "from_name": actor.full_name,
                "from_registration_number": actor.registration_number,
            },
            # One per person per day per thing: the same key the cooldown
            # uses, so a retry cannot slip a second copy through.
            dedupe_key=f"nudge:{kind.value}:{entity_id}:{actor.id}:{now.date().isoformat()}",
        )

    db.add(
        Nudge(
            actor_id=actor.id,
            kind=kind,
            entity_id=entity_id,
            recipient_count=len(recipients),
        )
    )
    db.commit()
    return NudgeResult(kind=kind, recipients=len(recipients), next_allowed_at=now + COOLDOWN)


def can_nudge(db: Session, actor: User, kind: NudgeKind, entity_id: uuid.UUID) -> datetime | None:
    """When the next nudge about this is allowed, or None if it is allowed now.

    Lets the interface show a disabled button with a reason instead of
    offering an action that will be refused.
    """
    last = _last_nudge(db, actor, kind, entity_id)
    if last is None:
        return None
    nxt = last + COOLDOWN
    return nxt if nxt > datetime.now(UTC) else None


__all__ = [
    "COOLDOWN",
    "NoRecipientError",
    "NothingToNudgeAboutError",
    "NudgeResult",
    "NudgeTooSoonError",
    "can_nudge",
    "send",
]
