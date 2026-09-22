"""Deadline reminders.

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

from sqlalchemy import Row, select
from sqlalchemy.orm import Session

from app.modules.funding.models import FundingOpportunity, FundingStatus
from app.modules.notifications.models import NotificationType
from app.modules.notifications.service import notify
from app.modules.opportunities.models import Opportunity, OpportunityStatus
from app.modules.profiles.models import SavedItem

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
