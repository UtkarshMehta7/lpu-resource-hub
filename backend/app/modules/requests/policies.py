"""Who may ask whom, and who may move a request along.

Two separate rules, and the first is the one that earns the feature.

**Addressability** is `REQUEST_RECIPIENT_ROLES` plus a department check. A
sender may only reach roles above their own, and only inside their own
department unless the recipient answers to the institution rather than a
department. Without that pair, a recipient field is a route to message anyone
in the institution -- which is exactly what nudges were designed to avoid
(ADR 0031), and why this needs its own ADR to reverse it (ADR 0039).

**Transitions** are one table, checked for both actors, the same way
`milestones/policies.py:TRANSITIONS` serves members and owners. A move that
does not exist is 409 whoever asks; a move that exists but belongs to the
other party is 403. In that order -- the patent pipeline's rule.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import Session

from app.core.permissions import (
    INSTITUTION_WIDE_ROLES,
    REQUEST_RECIPIENT_ROLES,
)
from app.modules.requests.models import PersonalRequest, RequestStatus
from app.modules.users.models import User

#: Which side of the request a person is on. Not a role: the same coordinator
#: is a recipient of a student's request and a sender of their own.
Actor = Literal["sender", "recipient"]

#: The only authority on how a request moves.
#:
#: The recipient drives the institution's half -- taking it up, resolving it,
#: refusing it -- and the sender may only ever retract. Reopening a decided
#: request is deliberately absent: an answer has been given, and asking again
#: is a new request with its own date, not a mutation of the old one.
TRANSITIONS: dict[tuple[RequestStatus, RequestStatus], frozenset[Actor]] = {
    (RequestStatus.SUBMITTED, RequestStatus.UNDER_REVIEW): frozenset({"recipient"}),
    (RequestStatus.SUBMITTED, RequestStatus.RESOLVED): frozenset({"recipient"}),
    (RequestStatus.SUBMITTED, RequestStatus.DECLINED): frozenset({"recipient"}),
    (RequestStatus.UNDER_REVIEW, RequestStatus.RESOLVED): frozenset({"recipient"}),
    (RequestStatus.UNDER_REVIEW, RequestStatus.DECLINED): frozenset({"recipient"}),
    #: Putting it back down: "I looked, and it is not mine to decide yet."
    (RequestStatus.UNDER_REVIEW, RequestStatus.SUBMITTED): frozenset({"recipient"}),
    (RequestStatus.SUBMITTED, RequestStatus.WITHDRAWN): frozenset({"sender"}),
    (RequestStatus.UNDER_REVIEW, RequestStatus.WITHDRAWN): frozenset({"sender"}),
}

#: Statuses from which nothing further happens. Read off TRANSITIONS rather
#: than listed again, so a new move cannot leave this stale.
TERMINAL_STATUSES: frozenset[RequestStatus] = frozenset(
    status for status in RequestStatus if not any(start is status for start, _ in TRANSITIONS)
)


def actors_for(current: RequestStatus, target: RequestStatus) -> frozenset[Actor]:
    """Who, if anyone, may make this move. Empty means the move does not exist."""
    return TRANSITIONS.get((current, target), frozenset())


def side_of(request: PersonalRequest, viewer: User) -> Actor | None:
    """Which side this viewer is on, or None if the request is not theirs.

    Nobody else is a party to a request -- administrators included, unless
    they are the named recipient. A request is between two people, and a
    third reading it would make the channel useless for the thing it exists
    for.
    """
    if request.sender_id == viewer.id:
        return "sender"
    if request.recipient_id is not None and request.recipient_id == viewer.id:
        return "recipient"
    return None


def next_statuses(request: PersonalRequest, viewer: User) -> list[RequestStatus]:
    """The moves this reader may actually make, computed per reader.

    So the interface can never offer a step the service would refuse -- the
    same reason the patent pipeline computes `next_statuses` per reader
    instead of publishing one list for everybody.
    """
    side = side_of(request, viewer)
    if side is None:
        return []
    return [
        target
        for (start, target), actors in TRANSITIONS.items()
        if start is request.status and side in actors
    ]


def visibility_filter(viewer: User) -> ColumnElement[bool]:
    """The requests this person is a party to, as a filter.

    Used by every read path, so the list, the single read and the attachment
    download cannot disagree.
    """
    return or_(
        PersonalRequest.sender_id == viewer.id,
        PersonalRequest.recipient_id == viewer.id,
    )


def addressable_filter(sender: User) -> ColumnElement[bool]:
    """The people this sender may put a request to, as a filter.

    The candidate list and the submit check are both built from this, so the
    picker can never offer somebody the submit would refuse -- the same
    discipline `manageable_facility_filter` and the custodian-candidate list
    hold, where a queue that showed a request the approve call would reject
    was the bug worth preventing.
    """
    roles = REQUEST_RECIPIENT_ROLES[sender.role]
    if not roles:
        # An administrator addresses nobody. `in_(())` is valid SQL but reads
        # as an oversight; say it outright.
        return or_(False)

    scope: ColumnElement[bool] = User.role.in_(INSTITUTION_WIDE_ROLES & roles)
    departmental = roles - INSTITUTION_WIDE_ROLES
    if departmental and sender.department_id is not None:
        scope = or_(
            scope,
            and_(
                User.role.in_(departmental),
                User.department_id == sender.department_id,
            ),
        )
    return and_(
        scope,
        User.is_active.is_(True),
        # Nobody asks themselves, which also keeps a coordinator from
        # appearing in their own candidate list once a dean is involved.
        User.id != sender.id,
    )


def may_address(db: Session, sender: User, recipient_id: object) -> bool:
    """Whether this exact person is addressable, asked of the same filter.

    Not a second opinion built from the role alone: the department check has
    to run against the stored row, or a sender could name a coordinator from
    another school whose role happens to be permitted.
    """
    return (
        db.execute(
            select(User.id).where(User.id == recipient_id, addressable_filter(sender))
        ).scalar_one_or_none()
        is not None
    )
