"""What may happen to a suspected duplicate, in one table.

One transition table per workflow, enforced in the service -- the same shape
as projects, bookings and milestones.
"""

from __future__ import annotations

from app.modules.deduplication.models import DuplicateStatus

PENDING = DuplicateStatus.SUSPECTED
MERGED = DuplicateStatus.MERGED
SEPARATE = DuplicateStatus.SEPARATE
IGNORED = DuplicateStatus.IGNORED

#: Every decision is revisitable, because every one of them is a judgement
#: somebody could have got wrong. Returning to SUSPECTED is how a merge is
#: undone and how a dismissal is reopened; the service restores the deleted
#: record from its snapshot when leaving MERGED.
TRANSITIONS: frozenset[tuple[DuplicateStatus, DuplicateStatus]] = frozenset(
    {
        (PENDING, MERGED),
        (PENDING, SEPARATE),
        (PENDING, IGNORED),
        (IGNORED, MERGED),
        (IGNORED, SEPARATE),
        (IGNORED, PENDING),
        (SEPARATE, PENDING),
        (MERGED, PENDING),
    }
)


class InvalidTransitionError(Exception):
    """That is not a move this workflow allows."""


def assert_transition(current: DuplicateStatus, target: DuplicateStatus) -> None:
    if (current, target) not in TRANSITIONS:
        raise InvalidTransitionError


__all__ = ["TRANSITIONS", "InvalidTransitionError", "assert_transition"]
