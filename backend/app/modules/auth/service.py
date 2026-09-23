"""Registration, login and refresh-token rotation with reuse detection.

Services never import FastAPI; the router maps the exceptions raised here to
HTTP status codes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.modules.auth.models import RefreshToken
from app.modules.auth.schemas import RegisterRequest
from app.modules.users.models import User, UserRole
from app.modules.users.service import get_by_id, get_by_registration_number


class RegistrationNumberTakenError(Exception):
    """Raised when the registration number (or email) is already taken."""


class InvalidCredentialsError(Exception):
    """Failed login: unknown registration number or wrong password.

    Registration numbers are semi-public and sequential, so the message must
    never distinguish "no such account" from "wrong password" -- otherwise
    the login form becomes a roster-enumeration oracle.
    """


class InvalidRefreshTokenError(Exception):
    """Refresh token missing, unknown, expired, or already rotated out (possible theft)."""


class IncorrectPasswordError(Exception):
    """Raised by change_password when current_password does not match."""


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int


def register_user(db: Session, data: RegisterRequest) -> User:
    user = User(
        registration_number=data.registration_number,
        email=data.email.lower() if data.email else None,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=UserRole(data.role),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise RegistrationNumberTakenError from exc
    db.refresh(user)
    return user


def authenticate(db: Session, registration_number: str, password: str) -> User:
    user = get_by_registration_number(db, registration_number)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError
    return user


def issue_tokens(db: Session, user: User, settings: Settings) -> IssuedTokens:
    """Issue tokens for a fresh session (new login or registration): a new token family."""
    access_token = create_access_token(user.id, user.role.value, settings)
    _, raw_refresh = _create_refresh_token_row(db, user, uuid.uuid4(), settings)
    db.commit()
    return IssuedTokens(access_token, raw_refresh, settings.access_token_expire_minutes * 60)


def rotate_refresh_token(
    db: Session, raw_token: str, settings: Settings
) -> tuple[User, IssuedTokens]:
    existing = _find_by_raw_token(db, raw_token)
    if existing is None:
        raise InvalidRefreshTokenError

    if existing.revoked_at is not None:
        # The token was already rotated out (or explicitly logged out) and is
        # being presented again: treat as theft/replay and kill the family.
        _revoke_family(db, existing.family_id)
        db.commit()
        raise InvalidRefreshTokenError

    if existing.expires_at < datetime.now(UTC):
        raise InvalidRefreshTokenError

    user = get_by_id(db, existing.user_id)
    if user is None or not user.is_active:
        raise InvalidRefreshTokenError

    access_token = create_access_token(user.id, user.role.value, settings)
    new_row, raw_refresh = _create_refresh_token_row(db, user, existing.family_id, settings)
    existing.revoked_at = datetime.now(UTC)
    existing.replaced_by_id = new_row.id
    db.commit()

    tokens = IssuedTokens(access_token, raw_refresh, settings.access_token_expire_minutes * 60)
    return user, tokens


def logout(db: Session, raw_token: str) -> None:
    """Revoke only the presented token, so other sessions/devices stay signed in."""
    existing = _find_by_raw_token(db, raw_token)
    if existing is None or existing.revoked_at is not None:
        return
    existing.revoked_at = datetime.now(UTC)
    db.commit()


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    """Changes the password and signs out every session (all refresh tokens revoked)."""
    if not verify_password(current_password, user.password_hash):
        raise IncorrectPasswordError

    user.password_hash = hash_password(new_password)
    # Whatever temporary password they were given is now gone.
    user.must_change_password = False
    revoke_all_sessions(db, user.id)
    db.commit()


def revoke_all_sessions(db: Session, user_id: uuid.UUID) -> None:
    """Revokes every non-revoked refresh token for a user. Does not commit."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


def _find_by_raw_token(db: Session, raw_token: str) -> RefreshToken | None:
    token_hash = hash_refresh_token(raw_token)
    return db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalar_one_or_none()


def _create_refresh_token_row(
    db: Session, user: User, family_id: uuid.UUID, settings: Settings
) -> tuple[RefreshToken, str]:
    raw_refresh = generate_refresh_token()
    row = RefreshToken(
        user_id=user.id,
        family_id=family_id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(row)
    db.flush()
    return row, raw_refresh


def _revoke_family(db: Session, family_id: uuid.UUID) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
