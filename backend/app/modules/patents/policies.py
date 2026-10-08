"""Who may move an invention along, and which moves exist.

One pipeline, two halves, and **two actors** -- the shape the milestones
module already uses, for the same reason: a transition table that ignores who
is asking answers only half the question.

* The university's half (disclosed -> assessed -> approved or declined) is the
  IP cell's. An inventor may submit and may withdraw, and nothing else.
* The office's half (filed -> published -> granted ...) is the inventor's to
  record, because they are the one who hears from the office.

`verification_status` is a third, independent question -- is this RECORD
accurate -- and is decided in the service, not here.
"""

from __future__ import annotations

from typing import Literal

from app.modules.patents.models import PatentStatus
from app.modules.profiles.models import VerificationStatus
from app.modules.users.models import User, UserRole

Actor = Literal["inventor", "ip_cell"]


class InvalidTransitionError(Exception):
    """That is not a move the process allows from here."""


class NotAllowedActorError(Exception):
    """That move exists, but not for this person."""


#: (from, to) -> who may make the move.
#:
#: LAPSED -> GRANTED exists because paying a renewal fee late really does
#: restore a patent. DECLINED, REJECTED and WITHDRAWN are terminal: a fresh
#: attempt is a new disclosure, not this one reopened, and that matters --
#: the filing date it would eventually get is a different date.
TRANSITIONS: dict[tuple[PatentStatus, PatentStatus], frozenset[Actor]] = {
    # --- inside the university
    (PatentStatus.DISCLOSED, PatentStatus.UNDER_ASSESSMENT): frozenset({"ip_cell"}),
    (PatentStatus.DISCLOSED, PatentStatus.WITHDRAWN): frozenset({"inventor"}),
    (PatentStatus.UNDER_ASSESSMENT, PatentStatus.APPROVED_TO_FILE): frozenset({"ip_cell"}),
    (PatentStatus.UNDER_ASSESSMENT, PatentStatus.DECLINED): frozenset({"ip_cell"}),
    # Sending it back for more detail is a real outcome, not a failure.
    (PatentStatus.UNDER_ASSESSMENT, PatentStatus.DISCLOSED): frozenset({"ip_cell"}),
    (PatentStatus.UNDER_ASSESSMENT, PatentStatus.WITHDRAWN): frozenset({"inventor"}),
    (PatentStatus.APPROVED_TO_FILE, PatentStatus.WITHDRAWN): frozenset({"inventor"}),
    # --- at the office. The inventor records what the office did.
    (PatentStatus.APPROVED_TO_FILE, PatentStatus.FILED): frozenset({"inventor", "ip_cell"}),
    (PatentStatus.FILED, PatentStatus.PUBLISHED): frozenset({"inventor", "ip_cell"}),
    (PatentStatus.FILED, PatentStatus.WITHDRAWN): frozenset({"inventor", "ip_cell"}),
    (PatentStatus.FILED, PatentStatus.REJECTED): frozenset({"inventor", "ip_cell"}),
    (PatentStatus.PUBLISHED, PatentStatus.GRANTED): frozenset({"inventor", "ip_cell"}),
    (PatentStatus.PUBLISHED, PatentStatus.REJECTED): frozenset({"inventor", "ip_cell"}),
    (PatentStatus.PUBLISHED, PatentStatus.WITHDRAWN): frozenset({"inventor", "ip_cell"}),
    (PatentStatus.GRANTED, PatentStatus.LAPSED): frozenset({"inventor", "ip_cell"}),
    (PatentStatus.LAPSED, PatentStatus.GRANTED): frozenset({"inventor", "ip_cell"}),
}

#: Statuses that cannot be entered without the date that proves them. The
#: database carries the same rules as CHECKs; these turn them into sentences.
DATE_REQUIRED: dict[PatentStatus, str] = {
    PatentStatus.FILED: "filing_date",
    PatentStatus.PUBLISHED: "publication_date",
    PatentStatus.GRANTED: "grant_date",
}

NUMBER_FIELD: dict[PatentStatus, str] = {
    PatentStatus.FILED: "application_number",
    PatentStatus.PUBLISHED: "publication_number",
    PatentStatus.GRANTED: "grant_number",
}

#: Declining without a reason is what stops the next person disclosing.
NOTE_REQUIRED: frozenset[PatentStatus] = frozenset({PatentStatus.DECLINED})

#: Everything still inside the university. Nothing here has a filing date.
BEFORE_THE_OFFICE: frozenset[PatentStatus] = frozenset(
    {
        PatentStatus.DISCLOSED,
        PatentStatus.UNDER_ASSESSMENT,
        PatentStatus.APPROVED_TO_FILE,
        PatentStatus.DECLINED,
    }
)


def actors_for(current: PatentStatus, target: PatentStatus) -> frozenset[Actor]:
    moves = TRANSITIONS.get((current, target))
    if moves is None:
        raise InvalidTransitionError
    return moves


def assert_may_move(
    current: PatentStatus, target: PatentStatus, *, is_creator: bool, reviewer: bool
) -> None:
    """Checked in this order on purpose.

    A move that does not exist is a 409 whoever asks; a move that exists but
    is somebody else's is a 403. Deciding the second first would tell an
    inventor that "granted -> disclosed" is merely above their pay grade.
    """
    allowed = actors_for(current, target)
    mine: set[Actor] = set()
    if is_creator:
        mine.add("inventor")
    if reviewer:
        mine.add("ip_cell")
    if not (allowed & mine):
        raise NotAllowedActorError


def _is(actor: Actor, is_creator: bool, reviewer: bool) -> bool:
    return is_creator if actor == "inventor" else reviewer


def next_statuses(current: PatentStatus, *, is_creator: bool, reviewer: bool) -> list[PatentStatus]:
    """What this person may do next -- never what somebody else may.

    The interface renders exactly this, so it can never offer a button the
    service would refuse.
    """
    return sorted(
        target
        for (source, target), actors in TRANSITIONS.items()
        if source is current and any(_is(actor, is_creator, reviewer) for actor in actors)
    )


def initial_verification(creator: User) -> VerificationStatus:
    """An administrator's record needs no verification, ever.

    The same reasoning as the researcher profiles: verification means somebody
    senior vouched for a record, and nobody is senior to an administrator.
    """
    if creator.role is UserRole.ADMIN:
        return VerificationStatus.VERIFIED
    return VerificationStatus.PENDING
