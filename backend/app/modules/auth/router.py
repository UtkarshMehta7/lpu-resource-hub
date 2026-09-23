"""Authentication endpoints, mounted under /api/v1/auth.

The refresh token never appears in a JSON body: it travels only as an
httpOnly cookie scoped to this router's own path, so client-side JavaScript
(and an XSS payload) cannot read it. /refresh and /logout also require a
custom `X-Requested-With` header as a CSRF defence: a cross-site HTML form
cannot set custom headers, but same-origin JavaScript (our own frontend) can.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import get_app_settings, get_authenticated_user
from app.core.rate_limit import enforce_auth_rate_limit
from app.db.session import get_db
from app.modules.auth.schemas import (
    AccessTokenResponse,
    ChangePasswordRequest,
    LoginRequest,
)
from app.modules.auth.service import (
    IncorrectPasswordError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    IssuedTokens,
    authenticate,
    change_password,
    issue_tokens,
    logout,
    rotate_refresh_token,
)
from app.modules.users.models import User
from app.modules.users.schemas import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=settings.refresh_token_expire_seconds,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.is_production,
        samesite=settings.refresh_cookie_samesite,
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.is_production,
        samesite=settings.refresh_cookie_samesite,
    )


def _token_response(user: User, tokens: IssuedTokens) -> AccessTokenResponse:
    return AccessTokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        user=UserRead.model_validate(user),
    )


def require_csrf_header(x_requested_with: Annotated[str | None, Header()] = None) -> None:
    if not x_requested_with:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing X-Requested-With header.",
        )


@router.post("/login", response_model=AccessTokenResponse)
def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AccessTokenResponse:
    enforce_auth_rate_limit(request, data.registration_number)
    try:
        user = authenticate(db, data.registration_number, data.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            # Deliberately identical whether the account exists or not.
            detail="Incorrect registration number or password.",
        ) from exc

    tokens = issue_tokens(db, user, settings)
    _set_refresh_cookie(response, tokens.refresh_token, settings)
    return _token_response(user, tokens)


@router.post(
    "/refresh", response_model=AccessTokenResponse, dependencies=[Depends(require_csrf_header)]
)
def refresh(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> AccessTokenResponse:
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token was provided."
        )
    try:
        user, tokens = rotate_refresh_token(db, refresh_token, settings)
    except InvalidRefreshTokenError as exc:
        _clear_refresh_cookie(response, settings)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        ) from exc

    _set_refresh_cookie(response, tokens.refresh_token, settings)
    return _token_response(user, tokens)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf_header)],
)
def logout_route(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> None:
    if refresh_token is not None:
        logout(db, refresh_token)
    _clear_refresh_cookie(response, settings)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password_route(
    data: ChangePasswordRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    current_user: Annotated[User, Depends(get_authenticated_user)],
) -> None:
    try:
        change_password(db, current_user, data.current_password, data.new_password)
    except IncorrectPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        ) from exc
    # Every refresh token was just revoked; clear this browser's own cookie too.
    _clear_refresh_cookie(response, settings)
