"""Account provisioning endpoint, mounted under /api/v1.

Not under /admin: every role above student uses it. What gets created is
decided by the caller's own role (see app/core/permissions.CREATABLE_ROLE),
not by anything in the request body.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.permissions import Permission, require_permission
from app.core.rate_limit import client_ip
from app.db.session import get_db
from app.modules.admin import accounts, promotions
from app.modules.admin.schemas import (
    AccountCreateRequest,
    AdminAccountCreateRequest,
    AdminUserRead,
    CreatedAccountRead,
    PromotionChallengeRead,
    PromotionConfirmRequest,
    StepDownRequest,
)
from app.modules.admin.service import UserNotFoundError, get_user_or_raise
from app.modules.users.models import User

router = APIRouter(tags=["accounts"])
# Admin-only operations that sit outside the ordinary hierarchy.
admin_router = APIRouter(prefix="/admin", tags=["admin"])


def _load_user(db: Session, user_id: uuid.UUID) -> User:
    try:
        return get_user_or_raise(db, user_id)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        ) from exc


Creator = Annotated[User, Depends(require_permission(Permission.USER_CREATE))]

_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    accounts.NotAllowedRoleError: (
        status.HTTP_403_FORBIDDEN,
        "Your role cannot create accounts.",
    ),
    accounts.OutOfScopeError: (
        status.HTTP_403_FORBIDDEN,
        "You can only add people to your own department.",
    ),
    accounts.NoDepartmentError: (
        status.HTTP_403_FORBIDDEN,
        "Your account is not in a department yet, so there is nowhere to add "
        "anyone. Set your department on your profile, then ask your research "
        "coordinator or an administrator to verify you.",
    ),
    # Naming only the coordinator was a dead end for anyone in a department
    # that has none: an admin can verify anybody, and has to be offered.
    accounts.NotVerifiedError: (
        status.HTTP_403_FORBIDDEN,
        "Your researcher profile has not been verified yet. Your department's "
        "research coordinator can verify it — or any administrator, if your "
        "department has no coordinator yet.",
    ),
    accounts.UnknownDepartmentError: (status.HTTP_404_NOT_FOUND, "Department not found."),
    accounts.DepartmentRequiredError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Choose the department this person belongs to.",
    ),
    accounts.RegistrationNumberTakenError: (
        status.HTTP_409_CONFLICT,
        "An account with this registration number already exists.",
    ),
}


@contextmanager
def _domain_errors() -> Iterator[None]:
    try:
        yield
    except tuple(_ERROR_MAP) as exc:
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from exc


@router.post("/users", response_model=CreatedAccountRead, status_code=status.HTTP_201_CREATED)
def create_account(
    data: AccountCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    creator: Creator,
) -> CreatedAccountRead:
    """Creates an account and returns its temporary password **once**.

    The new user must replace that password before they can use anything
    else, so it is safe to show but not to store.
    """
    with _domain_errors():
        created = accounts.create_account(
            db,
            creator,
            registration_number=data.registration_number,
            full_name=data.full_name,
            department_id=data.department_id,
            email=data.email,
            ip=client_ip(request),
        )
    return CreatedAccountRead(
        user=AdminUserRead.model_validate(created.user),
        temporary_password=created.temporary_password,
    )


_PROMOTION_ERRORS: dict[type[Exception], tuple[int, str]] = {
    promotions.SelfPromotionError: (
        status.HTTP_409_CONFLICT,
        "You cannot run this on your own account.",
    ),
    promotions.AlreadyAdminError: (status.HTTP_409_CONFLICT, "They are already an administrator."),
    promotions.InactiveTargetError: (
        status.HTTP_409_CONFLICT,
        "Reactivate the account before promoting it.",
    ),
    promotions.ChallengeNotFoundError: (
        status.HTTP_404_NOT_FOUND,
        "No confirmation is waiting for this person. Start one first.",
    ),
    promotions.ChallengeExpiredError: (
        status.HTTP_409_CONFLICT,
        "That confirmation expired. Start a new one.",
    ),
    promotions.TooManyAttemptsError: (
        status.HTTP_429_TOO_MANY_REQUESTS,
        "Too many wrong codes. Start a new confirmation.",
    ),
    promotions.WrongCodeError: (status.HTTP_403_FORBIDDEN, "That code is not right."),
    promotions.LastAdminError: (
        status.HTTP_409_CONFLICT,
        "You are the only active administrator. Promote someone else first.",
    ),
}


@contextmanager
def _promotion_errors() -> Iterator[None]:
    try:
        yield
    except tuple(_PROMOTION_ERRORS) as exc:
        code, detail = _PROMOTION_ERRORS[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from exc


@admin_router.post("/users", response_model=CreatedAccountRead, status_code=status.HTTP_201_CREATED)
def create_account_as_admin(
    data: AdminAccountCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_permission(Permission.USER_UPDATE_ROLE))],
) -> CreatedAccountRead:
    """Create an account of any role, outside the hierarchy.

    The ordinary path (POST /users) derives the role from the caller and is
    how the platform is meant to grow. This is the override for when it has
    to be bypassed -- a department with no coordinator yet, a correction --
    and it is audited as `user.created_by_admin` so it never looks like an
    ordinary appointment in the log.
    """
    with _domain_errors():
        created = accounts.create_account(
            db,
            actor,
            registration_number=data.registration_number,
            full_name=data.full_name,
            department_id=data.department_id,
            email=data.email,
            ip=client_ip(request),
            override_role=data.role,
        )
    return CreatedAccountRead(
        user=AdminUserRead.model_validate(created.user),
        temporary_password=created.temporary_password,
    )


@admin_router.post("/users/{user_id}/admin-promotion", response_model=PromotionChallengeRead)
def request_admin_promotion(
    user_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_permission(Permission.USER_UPDATE_ROLE))],
) -> PromotionChallengeRead:
    """Send a one-time code to the person being promoted."""
    target = _load_user(db, user_id)
    with _promotion_errors():
        challenge = promotions.request_promotion(db, actor, target, ip=client_ip(request))
    return PromotionChallengeRead(
        id=challenge.id,
        target_user_id=challenge.target_user_id,
        expires_at=challenge.expires_at,
    )


@admin_router.post("/users/{user_id}/admin-promotion/confirm", response_model=AdminUserRead)
def confirm_admin_promotion(
    user_id: uuid.UUID,
    data: PromotionConfirmRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_permission(Permission.USER_UPDATE_ROLE))],
) -> User:
    """Finish the promotion with the code the target read out."""
    target = _load_user(db, user_id)
    with _promotion_errors():
        return promotions.confirm_promotion(
            db, actor, target, code=data.code, ip=client_ip(request)
        )


@admin_router.post("/me/step-down", response_model=AdminUserRead)
def step_down_as_admin(
    data: StepDownRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_permission(Permission.USER_UPDATE_ROLE))],
) -> User:
    """Give up your own admin role, once somebody else holds it."""
    with _promotion_errors():
        return promotions.step_down(db, actor, new_role=data.new_role, ip=client_ip(request))
