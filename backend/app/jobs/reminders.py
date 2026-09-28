"""Deadline and milestone reminders.

A plain function, not a framework: `send_deadline_reminders(db, now)` is
called by the scheduler, a test, or by hand. It looks at what each user
saved and reminds them when a deadline is a set number of days away.

Idempotency comes from the notification's `dedupe_key` (user + thing + lead
time), backed by a partial unique index, so running the job twice an hour --
or twice a second -- can never produce a duplicate reminder.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Row, select
from sqlalchemy.orm import Session

from app.modules.funding.models import FundingOpportunity, FundingStatus
from app.modules.milestones.models import SETTLED_STATUSES, Milestone
from app.modules.notifications.models import NotificationType
from app.modules.notifications.service import notify
from app.modules.opportunities.models import Opportunity, OpportunityStatus
from app.modules.profiles.models import SavedItem
from app.modules.projects.models import Project, ProjectMember

# How many days before a deadline to remind. The roadmap asks for 7 and 1.
LEAD_DAYS = (7, 1)


def send_deadline_reminders(db: Session, now: datetime | None = None) -> int:
    """Reminds users about saved items whose deadline is exactly N days away.

    Returns the number of reminders written.
    """
    today = (now or datetime.now(UTC)).date()
    sent = 0
    for lead in LEAD_DAYS:
        target = today + timedelta(days=lead)
        sent += _remind_opportunities(db, target, lead)
        sent += _remind_funding(db, target, lead)
    db.commit()
    return sent


def _remind_opportunities(db: Session, target: date, lead: int) -> int:
    rows = db.execute(
        select(SavedItem.user_id, Opportunity.id, Opportunity.title)
        .join(Opportunity, Opportunity.id == SavedItem.opportunity_id)
        .where(
            Opportunity.status == OpportunityStatus.OPEN,
            Opportunity.deadline == target,
        )
    ).all()
    return _notify_all(db, rows, lead, kind="opportunity")


def _remind_funding(db: Session, target: date, lead: int) -> int:
    rows = db.execute(
        select(SavedItem.user_id, FundingOpportunity.id, FundingOpportunity.title)
        .join(FundingOpportunity, FundingOpportunity.id == SavedItem.funding_id)
        .where(
            FundingOpportunity.status == FundingStatus.OPEN,
            FundingOpportunity.deadline == target,
        )
    ).all()
    return _notify_all(db, rows, lead, kind="funding")


def _notify_all(
    db: Session, rows: Sequence[Row[tuple[uuid.UUID, uuid.UUID, str]]], lead: int, *, kind: str
) -> int:
    sent = 0
    for user_id, item_id, title in rows:
        created = notify(
            db,
            user_id=user_id,
            notification_type=NotificationType.DEADLINE_REMINDER,
            payload={
                "kind": kind,
                "item_id": str(item_id),
                "title": title,
                "days_left": lead,
            },
            dedupe_key=f"deadline:{kind}:{item_id}:{lead}",
        )
        if created is not None:
            sent += 1
    return sent


# --- milestones ------------------------------------------------------------


def send_milestone_reminders(db: Session, now: datetime | None = None) -> int:
    """Warn a project team about milestones falling due, and about late ones.

    This is the part of at-risk handling that genuinely needs a job. Whether a
    milestone *is* at risk is derived on every read and never stored (see
    app/modules/milestones/risk.py); what cannot be derived is having told
    somebody exactly once, and that is what the dedupe key buys.

    Returns the number of reminders written.
    """
    today = (now or datetime.now(UTC)).date()
    sent = 0
    for lead in LEAD_DAYS:
        sent += _remind_milestones_due(db, today + timedelta(days=lead), lead)
    sent += _remind_milestones_overdue(db, today)
    db.commit()
    return sent


def _milestone_audience(db: Session, project_id: uuid.UUID) -> list[uuid.UUID]:
    """The owner and every member -- a milestone is the team's problem."""
    owner_id = db.scalar(select(Project.owner_id).where(Project.id == project_id))
    members = db.scalars(
        select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)
    ).all()
    everyone = ([owner_id] if owner_id is not None else []) + list(members)
    return list(dict.fromkeys(everyone))


def _outstanding() -> Sequence[Any]:
    """Filters shared by both passes: live project, unfinished milestone."""
    return (
        Project.deleted_at.is_(None),
        Milestone.status.not_in(tuple(SETTLED_STATUSES)),
    )


def _remind_milestones_due(db: Session, target: date, lead: int) -> int:
    rows = db.execute(
        select(Milestone.id, Milestone.title, Milestone.project_id, Project.title)
        .join(Project, Project.id == Milestone.project_id)
        .where(*_outstanding(), Milestone.due_date == target)
    ).all()
    sent = 0
    for milestone_id, title, project_id, project_title in rows:
        for user_id in _milestone_audience(db, project_id):
            created = notify(
                db,
                user_id=user_id,
                notification_type=NotificationType.MILESTONE_DUE,
                payload={
                    "milestone_id": str(milestone_id),
                    "project_id": str(project_id),
                    "title": title,
                    "project_title": project_title,
                    "days_left": lead,
                },
                dedupe_key=f"milestone:due:{milestone_id}:{lead}",
            )
            if created is not None:
                sent += 1
    return sent


def _remind_milestones_overdue(db: Session, today: date) -> int:
    """One notification per milestone, ever -- not one per day it stays late.

    The dedupe key deliberately omits the date: a milestone three weeks late
    should not produce twenty-one identical rows in somebody's inbox.
    """
    rows = db.execute(
        select(Milestone.id, Milestone.title, Milestone.project_id, Project.title)
        .join(Project, Project.id == Milestone.project_id)
        .where(*_outstanding(), Milestone.due_date < today)
    ).all()
    sent = 0
    for milestone_id, title, project_id, project_title in rows:
        for user_id in _milestone_audience(db, project_id):
            created = notify(
                db,
                user_id=user_id,
                notification_type=NotificationType.MILESTONE_OVERDUE,
                payload={
                    "milestone_id": str(milestone_id),
                    "project_id": str(project_id),
                    "title": title,
                    "project_title": project_title,
                },
                dedupe_key=f"milestone:overdue:{milestone_id}",
            )
            if created is not None:
                sent += 1
    return sent
