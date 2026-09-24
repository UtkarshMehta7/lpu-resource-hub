"""In-process domain events.

Something happens in one module (an application is decided, a booking is
approved) and other modules want to react without the first one importing
them. Handlers run *synchronously, inside the caller's transaction*: a
notification is written by the same commit as the thing it describes, so
there is never a notification for an action that rolled back -- and never a
silently missing one either.

This is deliberately not a queue. If a handler raises, the whole action
fails, which is the right trade-off while the only subscriber is the
notification writer.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class EventName(StrEnum):
    APPLICATION_SUBMITTED = "application.submitted"
    APPLICATION_DECIDED = "application.decided"
    COLLABORATION_REQUESTED = "collaboration.requested"
    COLLABORATION_RESPONDED = "collaboration.responded"
    BOOKING_DECIDED = "booking.decided"
    PROJECT_REVIEWED = "project.reviewed"
    PROFILE_VERIFIED = "profile.verified"
    OPPORTUNITY_PUBLISHED = "opportunity.published"
    MESSAGE_SENT = "message.sent"


@dataclass(frozen=True, slots=True)
class Event:
    name: EventName
    # Who caused it (may be None for scheduled jobs).
    actor_id: uuid.UUID | None = None
    payload: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[Session, Event], None]


class EventBus:
    """Handlers keyed by event name. One instance per process."""

    def __init__(self) -> None:
        self._handlers: dict[EventName, list[Handler]] = defaultdict(list)

    def subscribe(self, name: EventName, handler: Handler) -> None:
        if handler not in self._handlers[name]:
            self._handlers[name].append(handler)

    def publish(self, db: Session, event: Event) -> None:
        for handler in self._handlers[event.name]:
            handler(db, event)

    def clear(self) -> None:
        """Test helper: forget every subscription."""
        self._handlers.clear()

    def handler_count(self, name: EventName) -> int:
        return len(self._handlers[name])


EVENT_BUS = EventBus()
