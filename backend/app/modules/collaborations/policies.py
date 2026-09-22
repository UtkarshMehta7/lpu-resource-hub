"""Collaboration request workflow and who may contact whom.

TRANSITIONS is the one place the workflow is defined: the recipient answers,
the sender can take the request back, and only while it's PENDING.
"""

from __future__ import annotations

from typing import Literal

from app.modules.collaborations.models import CollaborationStatus as S
from app.modules.users.models import UserRole

Actor = Literal["sender", "recipient"]

TRANSITIONS: dict[tuple[S, S], frozenset[Actor]] = {
    (S.PENDING, S.ACCEPTED): frozenset({"recipient"}),
    (S.PENDING, S.DECLINED): frozenset({"recipient"}),
    (S.PENDING, S.CANCELLED): frozenset({"sender"}),
}

RESEARCHER_ROLES = frozenset({UserRole.FACULTY, UserRole.RESEARCH_COORDINATOR})


class InvalidTransitionError(Exception):
    """The request isn't PENDING any more."""


class WrongPartyError(Exception):
    """A party to the request tried the other party's action."""


def assert_transition(current: S, target: S, actor: Actor) -> None:
    allowed = TRANSITIONS.get((current, target))
    if allowed is None:
        raise InvalidTransitionError
    if actor not in allowed:
        raise WrongPartyError


def can_contact(recipient_role: UserRole, recipient_discoverable: bool) -> bool:
    """Anyone may contact researchers; students only if they opted in to
    discovery; admins are never collaboration targets. The same rule applies
    to every sender (students included), so it never reveals more than the
    directory and student discovery already do."""
    if recipient_role in RESEARCHER_ROLES:
        return True
    if recipient_role is UserRole.STUDENT:
        return recipient_discoverable
    return False
