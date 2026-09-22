"""Application workflow: the one transition table, and who may apply.

"reviewer" is the opportunity's creator. Scoped coordinators and admins can
*read* applications but never decide them.
"""

from __future__ import annotations

from typing import Literal

from app.modules.applications.models import ApplicationStatus as S
from app.modules.opportunities.models import STUDENT_TYPES, OpportunityType
from app.modules.users.models import User, UserRole

Actor = Literal["reviewer", "applicant"]

TRANSITIONS: dict[tuple[S, S], frozenset[Actor]] = {
    (S.SUBMITTED, S.UNDER_REVIEW): frozenset({"reviewer"}),
    (S.SUBMITTED, S.SHORTLISTED): frozenset({"reviewer"}),
    (S.SUBMITTED, S.REJECTED): frozenset({"reviewer"}),
    (S.UNDER_REVIEW, S.SHORTLISTED): frozenset({"reviewer"}),
    (S.UNDER_REVIEW, S.ACCEPTED): frozenset({"reviewer"}),
    (S.UNDER_REVIEW, S.REJECTED): frozenset({"reviewer"}),
    (S.SHORTLISTED, S.ACCEPTED): frozenset({"reviewer"}),
    (S.SHORTLISTED, S.REJECTED): frozenset({"reviewer"}),
    # Withdrawal is only possible before a final decision.
    (S.SUBMITTED, S.WITHDRAWN): frozenset({"applicant"}),
    (S.UNDER_REVIEW, S.WITHDRAWN): frozenset({"applicant"}),
    (S.SHORTLISTED, S.WITHDRAWN): frozenset({"applicant"}),
}

FINAL_STATUSES = frozenset({S.ACCEPTED, S.REJECTED, S.WITHDRAWN})


class InvalidTransitionError(Exception):
    """The requested status change isn't in TRANSITIONS for this actor."""


class IneligibleApplicantError(Exception):
    """Students apply to student openings; faculty only to collaborations."""


def assert_transition(current: S, target: S, actor: Actor) -> None:
    if actor not in TRANSITIONS.get((current, target), frozenset()):
        raise InvalidTransitionError


def assert_eligible(applicant: User, opportunity_type: OpportunityType) -> None:
    if applicant.role is UserRole.STUDENT:
        allowed = opportunity_type in STUDENT_TYPES
    elif applicant.role in (UserRole.FACULTY, UserRole.RESEARCH_COORDINATOR):
        allowed = opportunity_type is OpportunityType.COLLABORATION
    else:
        allowed = False
    if not allowed:
        raise IneligibleApplicantError
