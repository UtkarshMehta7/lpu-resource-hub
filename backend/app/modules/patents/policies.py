"""Who may do what to a patent record, and which status moves are legal.

Two workflows run on one row and they are deliberately kept apart:

* `PatentStatus` is **where the application has got to at the patent office**.
  The office decides it; we only record it. Its transitions are the ones the
  real process allows.
* `VerificationStatus` is **whether this institution has vouched for the
  record**. A granted patent can still be entered here with the wrong number,
  the wrong inventors or somebody else's invention.

Collapsing them would mean a coordinator's approval and a patent office's
grant were the same event, which they are not.
"""

from __future__ import annotations

from app.modules.patents.models import PatentStatus
from app.modules.profiles.models import VerificationStatus
from app.modules.users.models import User, UserRole


class InvalidTransitionError(Exception):
    """That is not a move the patent process allows from here."""


#: The legal lifecycle. Read as "from -> the states it may move to".
#:
#: LAPSED -> GRANTED exists because a lapsed patent really can be restored
#: when the renewal fee is paid late; it is not a mistake being undone.
#: REJECTED and WITHDRAWN are terminal: a fresh application is a new record
#: with a new filing date, not this one reopened.
TRANSITIONS: dict[PatentStatus, frozenset[PatentStatus]] = {
    PatentStatus.FILED: frozenset(
        {PatentStatus.PUBLISHED, PatentStatus.WITHDRAWN, PatentStatus.REJECTED}
    ),
    PatentStatus.PUBLISHED: frozenset(
        {PatentStatus.GRANTED, PatentStatus.REJECTED, PatentStatus.WITHDRAWN}
    ),
    PatentStatus.GRANTED: frozenset({PatentStatus.LAPSED}),
    PatentStatus.LAPSED: frozenset({PatentStatus.GRANTED}),
    PatentStatus.REJECTED: frozenset(),
    PatentStatus.WITHDRAWN: frozenset(),
}

#: Statuses that cannot be entered without the date that proves them. The
#: database carries the same rule as a CHECK; this is what turns it into an
#: error message instead of an IntegrityError.
DATE_REQUIRED: dict[PatentStatus, str] = {
    PatentStatus.PUBLISHED: "publication_date",
    PatentStatus.GRANTED: "grant_date",
}


def assert_transition_allowed(current: PatentStatus, target: PatentStatus) -> None:
    if target not in TRANSITIONS[current]:
        raise InvalidTransitionError


def initial_verification(creator: User) -> VerificationStatus:
    """An administrator's record needs no verification, ever.

    The same reasoning as the researcher profiles: verification means somebody
    senior vouched for a record, and nobody is senior to an administrator. A
    PENDING admin record would sit in a coordinator's queue asking them to
    vouch for their own senior.
    """
    if creator.role is UserRole.ADMIN:
        return VerificationStatus.VERIFIED
    return VerificationStatus.PENDING
