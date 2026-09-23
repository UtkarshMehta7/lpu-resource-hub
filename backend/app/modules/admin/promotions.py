"""Making someone an administrator, with the target's cooperation.

An admin can already do everything else alone. Handing out that same power is
the one action where a single compromised session should not be enough, so it
takes two people:

    admin opens a challenge  ->  a 6-digit code lands in the *target's* inbox
                             ->  the target reads it out
                             ->  the admin enters it and the promotion lands

The code is only ever stored as a SHA-256 hash, expires in ten minutes, works
once, and dies after five wrong guesses. Nothing here uses email or SMS: the
code travels through the notification system the platform already has, which
keeps the whole thing free and inside one database transaction.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.admin.models import AdminPromotion
from app.modules.audit import service as audit_service
from app.modules.notifications import service as notification_service
from app.modules.notifications.models import NotificationType
from app.modules.users.models import User, UserRole

CODE_LENGTH = 6
CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5


class AlreadyAdminError(Exception):
    """The target already holds the role."""


class SelfPromotionError(Exception):
    """An admin cannot run the ceremony on themselves."""


class InactiveTargetError(Exception):
    """A deactivated account must be reactivated before it can be promoted."""


class ChallengeNotFoundError(Exception):
    """No live challenge for this target."""


class ChallengeExpiredError(Exception):
    """The window closed, or the code was already used."""


class TooManyAttemptsError(Exception):
    """Burned through the guesses."""


class WrongCodeError(Exception):
    """The digits don't match."""


class LastAdminError(Exception):
    """Stepping down would leave the platform with nobody in charge."""


@dataclass(frozen=True, slots=True)
class OpenChallenge:
    """What the requester learns. Deliberately not the code."""

    id: uuid.UUID
    target_user_id: uuid.UUID
    expires_at: datetime


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def generate_code() -> str:
    """Six digits, uniformly random, leading zeros allowed."""
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def request_promotion(db: Session, actor: User, target: User, *, ip: str | None) -> OpenChallenge:
    """Open a challenge and send the code to the target."""
    if target.id == actor.id:
        raise SelfPromotionError
    if target.role is UserRole.ADMIN:
        raise AlreadyAdminError
    if not target.is_active:
        raise InactiveTargetError

    # A second request supersedes the first, so a mistyped target or a lost
    # code is recoverable without waiting out the TTL.
    for stale in db.execute(
        select(AdminPromotion).where(
            AdminPromotion.target_user_id == target.id,
            AdminPromotion.consumed_at.is_(None),
        )
    ).scalars():
        stale.consumed_at = datetime.now(UTC)

    code = generate_code()
    challenge = AdminPromotion(
        target_user_id=target.id,
        requested_by=actor.id,
        code_hash=_hash(code),
        expires_at=datetime.now(UTC) + CODE_TTL,
    )
    db.add(challenge)
    db.flush()

    notification_service.notify(
        db,
        user_id=target.id,
        notification_type=NotificationType.ADMIN_PROMOTION_CODE,
        payload={
            "code": code,
            "requested_by": actor.full_name,
            "expires_at": challenge.expires_at.isoformat(),
            "message": (
                f"{actor.full_name} wants to make you an administrator. "
                f"Your confirmation code is {code}. Only share it if you expect this."
            ),
        },
    )
    audit_service.record(
        db,
        actor_id=actor.id,
        action="user.admin_promotion_requested",
        entity_type="user",
        entity_id=target.id,
        before={"role": target.role.value},
        after=None,
        ip=ip,
    )
    db.commit()
    db.refresh(challenge)
    return OpenChallenge(id=challenge.id, target_user_id=target.id, expires_at=challenge.expires_at)


def confirm_promotion(db: Session, actor: User, target: User, *, code: str, ip: str | None) -> User:
    """Finish the promotion, if the digits match a live challenge."""
    challenge = (
        db.execute(
            select(AdminPromotion)
            .where(
                AdminPromotion.target_user_id == target.id,
                AdminPromotion.consumed_at.is_(None),
            )
            .order_by(AdminPromotion.created_at.desc())
        )
        .scalars()
        .first()
    )
    if challenge is None:
        raise ChallengeNotFoundError
    if challenge.expires_at <= datetime.now(UTC):
        raise ChallengeExpiredError
    if challenge.attempts >= MAX_ATTEMPTS:
        raise TooManyAttemptsError

    if not secrets.compare_digest(challenge.code_hash, _hash(code.strip())):
        challenge.attempts += 1
        # Count the guess even though the request fails, so a brute force
        # runs out whether or not the caller retries in one transaction.
        db.commit()
        raise WrongCodeError

    challenge.consumed_at = datetime.now(UTC)
    before = {"role": target.role.value}
    target.role = UserRole.ADMIN
    db.flush()
    audit_service.record(
        db,
        actor_id=actor.id,
        action="user.promoted_to_admin",
        entity_type="user",
        entity_id=target.id,
        before=before,
        after={"role": UserRole.ADMIN.value, "challenge_id": str(challenge.id)},
        ip=ip,
    )
    db.commit()
    db.refresh(target)
    return target


def step_down(db: Session, actor: User, *, new_role: UserRole, ip: str | None) -> User:
    """Give up your own admin role.

    Deliberately its own action rather than a self-service role change: the
    only role you may set on yourself is a lower one, and only while somebody
    else is still holding the platform.
    """
    if new_role is UserRole.ADMIN:
        raise AlreadyAdminError
    remaining = (
        db.execute(
            select(User).where(
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
                User.id != actor.id,
            )
        )
        .scalars()
        .first()
    )
    if remaining is None:
        raise LastAdminError

    before = {"role": actor.role.value}
    actor.role = new_role
    db.flush()
    audit_service.record(
        db,
        actor_id=actor.id,
        action="user.stepped_down",
        entity_type="user",
        entity_id=actor.id,
        before=before,
        after={"role": new_role.value},
        ip=ip,
    )
    db.commit()
    db.refresh(actor)
    return actor
