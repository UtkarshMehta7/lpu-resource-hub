"""Admin user-management endpoints, mounted under /api/v1/admin."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import client_ip
from app.db.session import get_db
from app.modules.admin.policies import LastActiveAdminError, SelfRoleChangeError
from app.modules.admin.schemas import AdminUserRead, AdminUserUpdate, RoleChangeRequest
from app.modules.admin.service import (
    UserNotFoundError,
    change_role,
    get_user_or_raise,
    list_users,
    set_active,
    update_user,
)
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/users", tags=["admin"])


def _load_target(db: Annotated[Session, Depends(get_db)], user_id: uuid.UUID) -> User:
    try:
        return get_user_or_raise(db, user_id)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        ) from exc


@router.get(
    "",
    response_model=Page[AdminUserRead],
    dependencies=[Depends(require_permission(Permission.USER_LIST))],
)
def read_users(
    db: Annotated[Session, Depends(get_db)],
    params: Annotated[PageParams, Depends()],
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> Page[AdminUserRead]:
    return list_users(db, params, role=role, is_active=is_active)


@router.patch(
    "/{user_id}",
    response_model=AdminUserRead,
    dependencies=[Depends(require_permission(Permission.USER_UPDATE))],
)
def patch_user(
    user_id: uuid.UUID,
    data: AdminUserUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    target = _load_target(db, user_id)
    return update_user(db, target, data)


@router.post("/{user_id}/role", response_model=AdminUserRead)
def change_user_role(
    user_id: uuid.UUID,
    data: RoleChangeRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_permission(Permission.USER_UPDATE_ROLE))],
) -> User:
    target = _load_target(db, user_id)
    try:
        return change_role(db, actor, target, data.role, ip=client_ip(request))
    except SelfRoleChangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="You cannot change your own role."
        ) from exc
    except LastActiveAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This would leave the platform with no active admin.",
        ) from exc


@router.post("/{user_id}/activate", response_model=AdminUserRead)
def activate_user(
    user_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_permission(Permission.USER_ACTIVATE))],
) -> User:
    target = _load_target(db, user_id)
    return set_active(db, actor, target, True, ip=client_ip(request))


@router.post("/{user_id}/deactivate", response_model=AdminUserRead)
def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_permission(Permission.USER_DEACTIVATE))],
) -> User:
    target = _load_target(db, user_id)
    try:
        return set_active(db, actor, target, False, ip=client_ip(request))
    except LastActiveAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This would leave the platform with no active admin.",
        ) from exc
