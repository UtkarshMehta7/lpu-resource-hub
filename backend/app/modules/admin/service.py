"""Admin user management: list, update, role changes, activation.

Services never import FastAPI; the router maps exceptions to HTTP status
codes. Every mutation writes an audit_logs row (see app/modules/audit).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams
from app.modules.admin.policies import (
    assert_not_self_role_change,
    assert_preserves_last_active_admin,
)
from app.modules.admin.schemas import AdminUserRead, AdminUserUpdate
from app.modules.audit import service as audit_service
from app.modules.auth.service import revoke_all_sessions
from app.modules.users.models import User, UserRole
from app.modules.users.service import get_by_id


class UserNotFoundError(Exception):
    """Raised when the target user id does not exist."""


def list_users(
    db: Session,
    params: PageParams,
    *,
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> Page[AdminUserRead]:
    query = select(User)
    if role is not None:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = (
        db.execute(
            query.order_by(User.created_at.desc()).offset(params.offset).limit(params.page_size)
        )
        .scalars()
        .all()
    )
    return Page[AdminUserRead](
        items=[AdminUserRead.model_validate(row) for row in rows],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )


def get_user_or_raise(db: Session, user_id: uuid.UUID) -> User:
    user = get_by_id(db, user_id)
    if user is None:
        raise UserNotFoundError
    return user


def update_user(db: Session, target: User, data: AdminUserUpdate) -> User:
    fields_set = data.model_fields_set
    if data.full_name is not None:
        target.full_name = data.full_name
    if "coordinator_scope_type" in fields_set:
        target.coordinator_scope_type = data.coordinator_scope_type
    if "coordinator_scope_id" in fields_set:
        target.coordinator_scope_id = data.coordinator_scope_id
    db.commit()
    db.refresh(target)
    return target


def change_role(
    db: Session, actor: User, target: User, new_role: UserRole, *, ip: str | None
) -> User:
    assert_not_self_role_change(actor, target)
    assert_preserves_last_active_admin(db, target, new_role=new_role)

    before = {"role": target.role.value}
    target.role = new_role
    db.flush()
    audit_service.record(
        db,
        actor_id=actor.id,
        action="user.role_changed",
        entity_type="user",
        entity_id=target.id,
        before=before,
        after={"role": target.role.value},
        ip=ip,
    )
    db.commit()
    db.refresh(target)
    return target


def set_active(db: Session, actor: User, target: User, is_active: bool, *, ip: str | None) -> User:
    assert_preserves_last_active_admin(db, target, new_is_active=is_active)

    before = {"is_active": target.is_active}
    target.is_active = is_active
    if not is_active:
        revoke_all_sessions(db, target.id)
    db.flush()
    audit_service.record(
        db,
        actor_id=actor.id,
        action="user.activated" if is_active else "user.deactivated",
        entity_type="user",
        entity_id=target.id,
        before=before,
        after={"is_active": target.is_active},
        ip=ip,
    )
    db.commit()
    db.refresh(target)
    return target
