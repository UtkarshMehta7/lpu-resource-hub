"""A published opening goes on the board (ADR 0041).

Subscribed to `OPPORTUNITY_PUBLISHED` and `OPPORTUNITY_CLOSED`, so nothing in
the opportunities module knows that announcements exist. The event was already
there -- it is what tells people whose profile matches -- and this is a second
listener on it rather than a new call from one module into another.

Three things make raising a notice automatically safe, given that
`ANNOUNCEMENT_POST` is deliberately withheld from faculty (ADR 0038):

1. **The reach is the opening's, not the poster's.** `reach_of` gives an
   institution-wide role the institution; this does not use it. A notice
   raised here is addressed to the DEPARTMENT the opening already belongs to,
   so publishing an opening cannot hand a faculty member a megaphone they do
   not otherwise have.
2. **Nothing here is free text.** Subject and body are derived from the
   opening. This is not a route by which somebody says an arbitrary thing to
   their department.
3. **One notice per opening, ever**, enforced by a UNIQUE constraint rather
   than by a check in this file.

And it must never break publishing: the whole thing runs in a savepoint that
swallows `SQLAlchemyError`, like the thread opened on acceptance. Posting an
opening is the older and more important act, and a new dependency from old
code to a new table does not get to 500 it.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.events import EVENT_BUS, Event, EventBus, EventName
from app.modules.announcements.models import (
    Announcement,
    AnnouncementAudience,
    AnnouncementStatus,
)
from app.modules.opportunities.models import Opportunity
from app.modules.users.models import User

logger = logging.getLogger(__name__)

#: Reads on the board, where the notice is one line among notices about
#: deadlines and policy. "Opening" says what kind of thing it is without
#: repeating the title.
_SUBJECT = "Opening: {title}"


def _body(opportunity: Opportunity, poster_name: str) -> str:
    lines = [
        f"{poster_name} has posted an opening: {opportunity.title}.",
        "",
        opportunity.description.strip(),
        "",
        f"Places: {opportunity.positions}.",
        f"Apply by {opportunity.deadline.isoformat()}.",
    ]
    if opportunity.eligibility:
        lines.insert(4, f"Who it is open to: {opportunity.eligibility.strip()}")
    return "\n".join(lines)


def _raise_notice(db: Session, opportunity_id: uuid.UUID) -> None:
    opportunity = db.get(Opportunity, opportunity_id)
    if opportunity is None:
        return
    # Already on the board, so say nothing further. Today this cannot happen
    # -- `opportunities/policies.py:TRANSITIONS` has no CLOSED -> OPEN, so an
    # opening is published exactly once in its life -- and the UNIQUE
    # constraint would refuse a second row anyway. It is here so that adding
    # reopening later changes the workflow and not, silently, the board.
    already = db.execute(
        select(Announcement.id).where(Announcement.source_opportunity_id == opportunity.id)
    ).scalar_one_or_none()
    if already is not None:
        return

    poster = db.get(User, opportunity.created_by)
    if poster is None:
        return

    # DEPARTMENT whenever the opening has one, which is almost always: it is
    # taken from the project, or from the coordinator's own scope. An opening
    # belonging to no department is the only institution-wide case, and it is
    # one only a coordinator can create.
    audience = (
        AnnouncementAudience.DEPARTMENT
        if opportunity.department_id is not None
        else AnnouncementAudience.INSTITUTION
    )
    db.add(
        Announcement(
            subject=_SUBJECT.format(title=opportunity.title)[:200],
            body=_body(opportunity, poster.full_name),
            audience=audience,
            department_id=opportunity.department_id,
            posted_by=poster.id,
            # Frozen at post time like any notice, so a later promotion does
            # not retitle what was announced.
            posted_by_role=poster.role,
            posted_by_name=poster.full_name,
            status=AnnouncementStatus.PUBLISHED,
            published_at=datetime.now(UTC),
            source_opportunity_id=opportunity.id,
        )
    )
    db.flush()


def _withdraw_notice(db: Session, opportunity_id: uuid.UUID) -> None:
    """Take the notice down when the opening stops being one.

    A board advertising a closed or filled opening is worse than a board that
    never mentioned it: somebody reads it, goes to apply and finds a door that
    does not open. Withdrawn rather than deleted, because said to everybody is
    not unsayable -- the same reason the status exists at all.
    """
    row = db.execute(
        select(Announcement).where(
            Announcement.source_opportunity_id == opportunity_id,
            Announcement.status == AnnouncementStatus.PUBLISHED,
        )
    ).scalar_one_or_none()
    if row is None:
        return
    row.status = AnnouncementStatus.WITHDRAWN
    db.flush()


def _in_a_savepoint(
    db: Session,
    run: Callable[[Session, uuid.UUID], None],
    opportunity_id: uuid.UUID,
) -> None:
    try:
        with db.begin_nested():
            run(db, opportunity_id)
    except SQLAlchemyError:
        # Deliberately swallowed, like the thread opened on acceptance: the
        # opening is published either way, and a board that could take down
        # the act it reports on is worse than a board with a gap in it.
        logger.exception(
            "Could not update the board for opportunity %s; the opening is unaffected.",
            opportunity_id,
        )


def _on_opportunity_published(db: Session, event: Event) -> None:
    _in_a_savepoint(db, _raise_notice, event.payload["opportunity_id"])


def _on_opportunity_closed(db: Session, event: Event) -> None:
    _in_a_savepoint(db, _withdraw_notice, event.payload["opportunity_id"])


def register(bus: EventBus = EVENT_BUS) -> None:
    bus.subscribe(EventName.OPPORTUNITY_PUBLISHED, _on_opportunity_published)
    bus.subscribe(EventName.OPPORTUNITY_CLOSED, _on_opportunity_closed)


__all__ = ["register"]
