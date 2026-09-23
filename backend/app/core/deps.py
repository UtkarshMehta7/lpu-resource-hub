"""Shared request-scoped dependencies: the authenticated user."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import InvalidAccessTokenError, decode_access_token
from app.db.session import get_db
from app.modules.users.models import User
from app.modules.users.service import get_by_id

_AUTH_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_app_settings(request: Request) -> Settings:
    """Read the settings the running app was built with, not the process-wide cache.

    Mirrors ``get_engine``/``get_db`` in ``app/db/session.py``: each app
    instance (including test instances built with explicit ``Settings``)
    owns its own state instead of relying on ``get_settings()``'s cache.
    """
    settings: Settings = request.app.state.settings
    return settings


def _extract_bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise _AUTH_ERROR
    return header.removeprefix("Bearer ").strip()


def get_authenticated_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> User:
    """The signed-in user, even if they still owe us a password change.

    Only the few endpoints that must stay reachable in that state use this:
    reading your own account, and changing your password.
    """
    token = _extract_bearer_token(request)
    try:
        payload = decode_access_token(token, settings)
    except InvalidAccessTokenError as exc:
        raise _AUTH_ERROR from exc

    user = get_by_id(db, payload.user_id)
    if user is None or not user.is_active:
        raise _AUTH_ERROR
    return user


def get_current_user(
    current_user: Annotated[User, Depends(get_authenticated_user)],
) -> User:
    """The signed-in user, for everything else.

    An account created with a temporary password is walled off until that
    password is replaced: the rest of the API answers 403 with a code the
    frontend uses to send them to the change-password screen.
    """
    if current_user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="password_change_required",
        )
    return current_user
