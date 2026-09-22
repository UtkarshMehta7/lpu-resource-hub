"""Booking workflow.

TRANSITIONS is the one place the workflow is defined. The database, not this
table, is what guarantees two approved bookings never overlap.
"""

from __future__ import annotations

from typing import Literal

from app.modules.bookings.models import BookingStatus as S

Actor = Literal["owner", "approver"]

TRANSITIONS: dict[tuple[S, S], frozenset[Actor]] = {
    (S.PENDING, S.APPROVED): frozenset({"approver"}),
    (S.PENDING, S.REJECTED): frozenset({"approver"}),
    (S.PENDING, S.CANCELLED): frozenset({"owner"}),
    # An approved slot can be given back, but only before it starts.
    (S.APPROVED, S.CANCELLED): frozenset({"owner", "approver"}),
    (S.APPROVED, S.COMPLETED): frozenset({"owner", "approver"}),
}

# Statuses that still hold a slot the owner may hand back.
CANCELLABLE = frozenset({S.PENDING, S.APPROVED})


class InvalidTransitionError(Exception):
    """The requested status change isn't in TRANSITIONS for this actor."""


class WrongActorError(Exception):
    """The caller can see the booking but may not take this action."""


def assert_transition(current: S, target: S, actor: Actor) -> None:
    allowed = TRANSITIONS.get((current, target))
    if allowed is None:
        raise InvalidTransitionError
    if actor not in allowed:
        raise WrongActorError
