"""Admin user management: list, update, role changes, activation.

Services never import FastAPI; the router maps exceptions to HTTP status
codes. Every mutation writes an audit_logs row (see app/modules/audit).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams
from app.core.security import hash_password
from app.modules.admin.accounts import generate_temporary_password
from app.modules.admin.models import Department, School
from app.modules.admin.policies import (
    assert_not_self_password_reset,
    assert_not_self_role_change,
    assert_preserves_last_active_admin,
)
from app.modules.admin.schemas import (
    AdminUserRead,
    AdminUserUpdate,
    DepartmentCreate,
    DepartmentUpdate,
    SchoolCreate,
    SchoolUpdate,
)
from app.modules.audit import service as audit_service
from app.modules.auth.service import revoke_all_sessions
from app.modules.users.models import CoordinatorScopeType, User, UserRole
from app.modules.users.service import get_by_id


class UserNotFoundError(Exception):
    """Raised when the target user id does not exist."""


class InvalidCoordinatorScopeError(Exception):
    """Raised when coordinator_scope_id doesn't name a real department for the scope type."""


class InvalidDepartmentError(Exception):
    """Raised when department_id doesn't name a real department."""


class SchoolNotFoundError(Exception):
    """Raised when the target school id does not exist."""


class SchoolNameTakenError(Exception):
    """Raised when a school name is already in use."""


class DepartmentNotFoundError(Exception):
    """Raised when the target department id does not exist."""


class DepartmentNameTakenError(Exception):
    """Raised when a department name is already in use within its school."""


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


def _sync_coordinator_scope(target: User) -> None:
    """Keep a coordinator's authority in step with their department.

    A coordinator's scope is the whole of what they may do -- verify, review,
    approve, appoint. Setting the role or the department from the users page
    used to leave the scope untouched, so a coordinator created that way
    oversaw nothing: an empty verification queue and 403 on every decision,
    with nothing on screen explaining why.

    The platform only has department-level coordinators today (ADR 0015), so
    the scope is not an independent choice: it is the department. Setting it
    here means the two can never disagree again.
    """
    if target.role is UserRole.RESEARCH_COORDINATOR:
        target.coordinator_scope_type = CoordinatorScopeType.DEPARTMENT
        target.coordinator_scope_id = target.department_id
    else:
        # Someone who is no longer a coordinator oversees nothing.
        target.coordinator_scope_type = None
        target.coordinator_scope_id = None


def update_user(
    db: Session, actor: User, target: User, data: AdminUserUpdate, *, ip: str | None
) -> User:
    fields_set = data.model_fields_set
    if data.full_name is not None:
        target.full_name = data.full_name

    # A department decides what its members may reach, so a change to one is
    # audited like the other scope changes.
    department_changed = (
        "department_id" in fields_set and data.department_id != target.department_id
    )
    if department_changed:
        if data.department_id is not None and db.get(Department, data.department_id) is None:
            raise InvalidDepartmentError
        before_department = target.department_id
        target.department_id = data.department_id
        # An explicit scope in the same request still wins; otherwise the new
        # department is what they oversee.
        if "coordinator_scope_id" not in fields_set:
            _sync_coordinator_scope(target)

    resulting_type = (
        data.coordinator_scope_type
        if "coordinator_scope_type" in fields_set
        else target.coordinator_scope_type
    )
    resulting_id = (
        data.coordinator_scope_id
        if "coordinator_scope_id" in fields_set
        else target.coordinator_scope_id
    )
    # Only DEPARTMENT is checked: SCHOOL/UNIVERSITY scopes exist in the
    # schema for later but there's nothing to validate against yet.
    if (
        resulting_type is CoordinatorScopeType.DEPARTMENT
        and resulting_id is not None
        and db.get(Department, resulting_id) is None
    ):
        raise InvalidCoordinatorScopeError

    if "coordinator_scope_type" in fields_set:
        target.coordinator_scope_type = data.coordinator_scope_type
    if "coordinator_scope_id" in fields_set:
        target.coordinator_scope_id = data.coordinator_scope_id

    if department_changed:
        db.flush()
        audit_service.record(
            db,
            actor_id=actor.id,
            action="user.department_changed",
            entity_type="user",
            entity_id=target.id,
            before={"department_id": str(before_department) if before_department else None},
            after={"department_id": str(target.department_id) if target.department_id else None},
            ip=ip,
        )
    db.commit()
    db.refresh(target)
    return target


def reset_temporary_password(
    db: Session, actor: User, target: User, *, ip: str | None
) -> tuple[User, str]:
    """Issue a fresh temporary password for someone who lost theirs.

    The password is returned once and never stored in readable form. Every
    existing session is revoked, and the account is walled off behind the
    password-change gate again, exactly as a newly created one is.
    """
    assert_not_self_password_reset(actor, target)

    temporary_password = generate_temporary_password()
    target.password_hash = hash_password(temporary_password)
    target.must_change_password = True
    db.flush()
    revoke_all_sessions(db, target.id)
    audit_service.record(
        db,
        actor_id=actor.id,
        action="user.password_reset",
        entity_type="user",
        entity_id=target.id,
        before=None,
        after={"must_change_password": True},
        ip=ip,
    )
    db.commit()
    db.refresh(target)
    return target, temporary_password


def change_role(
    db: Session, actor: User, target: User, new_role: UserRole, *, ip: str | None
) -> User:
    assert_not_self_role_change(actor, target)
    assert_preserves_last_active_admin(db, target, new_role=new_role)

    before = {"role": target.role.value}
    target.role = new_role
    _sync_coordinator_scope(target)
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


def list_schools(db: Session) -> list[School]:
    return list(db.execute(select(School).order_by(School.name)).scalars().all())


def create_school(db: Session, data: SchoolCreate) -> School:
    school = School(name=data.name)
    db.add(school)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise SchoolNameTakenError from exc
    db.refresh(school)
    return school


def get_school_or_raise(db: Session, school_id: uuid.UUID) -> School:
    school = db.get(School, school_id)
    if school is None:
        raise SchoolNotFoundError
    return school


def update_school(db: Session, school: School, data: SchoolUpdate) -> School:
    if data.name is not None:
        school.name = data.name
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise SchoolNameTakenError from exc
    db.refresh(school)
    return school


def delete_school(db: Session, school: School) -> None:
    """Cascades to the school's departments; their users' department_id is set to null."""
    db.delete(school)
    db.commit()


def list_departments(db: Session, *, school_id: uuid.UUID | None = None) -> list[Department]:
    query = select(Department)
    if school_id is not None:
        query = query.where(Department.school_id == school_id)
    return list(db.execute(query.order_by(Department.name)).scalars().all())


def create_department(db: Session, data: DepartmentCreate) -> Department:
    if db.get(School, data.school_id) is None:
        raise SchoolNotFoundError

    department = Department(school_id=data.school_id, name=data.name)
    db.add(department)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DepartmentNameTakenError from exc
    db.refresh(department)
    return department


def get_department_or_raise(db: Session, department_id: uuid.UUID) -> Department:
    department = db.get(Department, department_id)
    if department is None:
        raise DepartmentNotFoundError
    return department


def update_department(db: Session, department: Department, data: DepartmentUpdate) -> Department:
    if data.name is not None:
        department.name = data.name
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DepartmentNameTakenError from exc
    db.refresh(department)
    return department


def delete_department(db: Session, department: Department) -> None:
    """Users in this department have their department_id set to null (ON DELETE SET NULL)."""
    db.delete(department)
    db.commit()
