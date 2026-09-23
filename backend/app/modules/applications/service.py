"""Applying to opportunities and deciding applications.

Who can see an application: the applicant, the opportunity's creator, the
coordinator whose department it belongs to, and admins. Anyone else gets
404. Only the creator decides; only the applicant withdraws.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.events import EVENT_BUS, Event, EventName
from app.modules.applications.models import Application, ApplicationEvent, ApplicationStatus
from app.modules.applications.policies import (
    assert_eligible,
    assert_transition,
)
from app.modules.applications.schemas import (
    ApplicationCreate,
    ApplicationEventRead,
    ApplicationRead,
    StatusChangeRequest,
)
from app.modules.audit import service as audit_service
from app.modules.opportunities import service as opportunity_service
from app.modules.opportunities.models import Opportunity, OpportunityStatus
from app.modules.opportunities.policies import actor_for
from app.modules.projects.models import ProjectMember
from app.modules.users.models import User


class ApplicationNotFoundError(Exception):
    """No such application, or the viewer may not know it exists."""


class OwnOpportunityError(Exception):
    """You can't apply to an opportunity you created."""


class NotOpenError(Exception):
    """The opportunity isn't accepting applications."""


class DuplicateApplicationError(Exception):
    """The caller already applied to this opportunity."""


class NotReviewerError(Exception):
    """Only the opportunity's creator may change an application's status."""


class NotApplicantError(Exception):
    """Only the applicant may withdraw."""


class PositionsFilledError(Exception):
    """Every position is already taken."""


class CannotViewApplicationsError(Exception):
    """The caller can see the opportunity but not its applications."""


# --- helpers -----------------------------------------------------------------


def _load(db: Session, viewer: User, application_id: uuid.UUID) -> tuple[Application, Opportunity]:
    row = db.execute(
        select(Application, Opportunity)
        .join(Opportunity, Opportunity.id == Application.opportunity_id)
        .where(Application.id == application_id)
    ).one_or_none()
    if row is None:
        raise ApplicationNotFoundError
    application, opportunity = row
    if application.applicant_id != viewer.id and actor_for(viewer, opportunity) is None:
        raise ApplicationNotFoundError
    return application, opportunity


def _to_reads(
    db: Session, rows: Sequence[tuple[Application, Opportunity]]
) -> list[ApplicationRead]:
    if not rows:
        return []
    ids = [a.id for a, _ in rows]
    events: dict[uuid.UUID, list[ApplicationEventRead]] = {i: [] for i in ids}
    for event in db.execute(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id.in_(ids))
        .order_by(ApplicationEvent.created_at)
    ).scalars():
        events[event.application_id].append(
            ApplicationEventRead(status=event.status, note=event.note, created_at=event.created_at)
        )
    names: dict[uuid.UUID, tuple[str, str]] = {
        uid: (name, number)
        for uid, name, number in db.execute(
            select(User.id, User.full_name, User.registration_number).where(
                User.id.in_({a.applicant_id for a, _ in rows})
            )
        ).all()
    }
    return [
        ApplicationRead(
            id=a.id,
            opportunity_id=o.id,
            opportunity_title=o.title,
            opportunity_type=o.opportunity_type,
            applicant_id=a.applicant_id,
            applicant_name=names.get(a.applicant_id, ("", ""))[0],
            applicant_registration_number=names.get(a.applicant_id, ("", ""))[1],
            statement=a.statement,
            status=a.status,
            note=a.note,
            decided_at=a.decided_at,
            created_at=a.created_at,
            events=events[a.id],
        )
        for a, o in rows
    ]


def _record_event(db: Session, application: Application, actor: User, note: str | None) -> None:
    db.add(
        ApplicationEvent(
            application_id=application.id, status=application.status, actor_id=actor.id, note=note
        )
    )


# --- operations --------------------------------------------------------------


def apply(
    db: Session, applicant: User, opportunity_id: uuid.UUID, data: ApplicationCreate
) -> ApplicationRead:
    opportunity = opportunity_service.load_visible(db, applicant, opportunity_id)
    if opportunity.created_by == applicant.id:
        raise OwnOpportunityError
    assert_eligible(applicant, opportunity.opportunity_type)
    if opportunity.status is not OpportunityStatus.OPEN:
        raise NotOpenError
    if opportunity.deadline < opportunity_service.today():
        raise opportunity_service.DeadlinePassedError

    application = Application(
        opportunity_id=opportunity.id, applicant_id=applicant.id, statement=data.statement
    )
    db.add(application)
    try:
        # The UNIQUE(opportunity_id, applicant_id) constraint is the real
        # guard: two concurrent submits can't both get here successfully.
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateApplicationError from exc
    application.status = ApplicationStatus.SUBMITTED
    _record_event(db, application, applicant, None)
    EVENT_BUS.publish(
        db,
        Event(
            name=EventName.APPLICATION_SUBMITTED,
            actor_id=applicant.id,
            payload={
                "recipient_id": opportunity.created_by,
                "application_id": application.id,
                "opportunity_id": opportunity.id,
                "opportunity_title": opportunity.title,
                "applicant_name": applicant.full_name,
            },
        ),
    )
    db.commit()
    db.refresh(application)
    return _to_reads(db, [(application, opportunity)])[0]


def get_application(db: Session, viewer: User, application_id: uuid.UUID) -> ApplicationRead:
    return _to_reads(db, [_load(db, viewer, application_id)])[0]


def my_applications(db: Session, applicant: User) -> list[ApplicationRead]:
    rows = db.execute(
        select(Application, Opportunity)
        .join(Opportunity, Opportunity.id == Application.opportunity_id)
        .where(Application.applicant_id == applicant.id)
        .order_by(Application.created_at.desc())
    ).all()
    return _to_reads(db, [(a, o) for a, o in rows])


def list_for_opportunity(
    db: Session, viewer: User, opportunity_id: uuid.UUID
) -> list[ApplicationRead]:
    opportunity = opportunity_service.load_visible(db, viewer, opportunity_id)
    if actor_for(viewer, opportunity) is None:
        raise CannotViewApplicationsError
    rows = db.execute(
        select(Application)
        .where(Application.opportunity_id == opportunity.id)
        .order_by(Application.created_at)
    ).scalars()
    return _to_reads(db, [(a, opportunity) for a in rows])


def change_status(
    db: Session,
    reviewer: User,
    application_id: uuid.UUID,
    data: StatusChangeRequest,
    *,
    ip: str | None,
) -> ApplicationRead:
    application, opportunity = _load(db, reviewer, application_id)
    if opportunity.created_by != reviewer.id:
        raise NotReviewerError
    assert_transition(application.status, data.status, "reviewer")

    accepting = data.status is ApplicationStatus.ACCEPTED
    if accepting and (
        opportunity.status is OpportunityStatus.FILLED
        or opportunity_service.accepted_count(db, opportunity.id) >= opportunity.positions
    ):
        raise PositionsFilledError

    before = application.status
    application.status = data.status
    application.note = data.note
    application.decided_by = reviewer.id
    application.decided_at = datetime.now(UTC)
    _record_event(db, application, reviewer, data.note)

    if accepting:
        db.flush()
        if data.add_to_project and opportunity.project_id is not None:
            already = db.execute(
                select(ProjectMember.id).where(
                    ProjectMember.project_id == opportunity.project_id,
                    ProjectMember.user_id == application.applicant_id,
                )
            ).scalar_one_or_none()
            if already is None:
                db.add(
                    ProjectMember(
                        project_id=opportunity.project_id,
                        user_id=application.applicant_id,
                        member_role=opportunity.opportunity_type.value.replace("_", " "),
                    )
                )
        opportunity_service.mark_filled_if_full(db, opportunity)

    EVENT_BUS.publish(
        db,
        Event(
            name=EventName.APPLICATION_DECIDED,
            actor_id=reviewer.id,
            payload={
                "recipient_id": application.applicant_id,
                "application_id": application.id,
                "opportunity_id": opportunity.id,
                "opportunity_title": opportunity.title,
                "status": data.status.value,
                "note": data.note,
            },
        ),
    )
    audit_service.record(
        db,
        actor_id=reviewer.id,
        action=f"application.{data.status.value}",
        entity_type="application",
        entity_id=application.id,
        before={"status": before.value},
        after={"status": data.status.value, "note": data.note},
        ip=ip,
    )
    # One commit: the decision, the timeline event, the team membership and
    # the FILLED transition succeed or fail together.
    db.commit()
    db.refresh(application)
    return _to_reads(db, [(application, opportunity)])[0]


def withdraw(
    db: Session, applicant: User, application_id: uuid.UUID, note: str | None
) -> ApplicationRead:
    application, opportunity = _load(db, applicant, application_id)
    if application.applicant_id != applicant.id:
        raise NotApplicantError
    assert_transition(application.status, ApplicationStatus.WITHDRAWN, "applicant")
    application.status = ApplicationStatus.WITHDRAWN
    _record_event(db, application, applicant, note)
    db.commit()
    db.refresh(application)
    return _to_reads(db, [(application, opportunity)])[0]
