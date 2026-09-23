"""Admin user-management endpoints, mounted under /api/v1/admin."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.pagination import Page, PageParams
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import client_ip
from app.db.session import get_db
from app.modules.admin.models import Department, School
from app.modules.admin.policies import (
    LastActiveAdminError,
    SelfPasswordResetError,
    SelfRoleChangeError,
)
from app.modules.admin.schemas import (
    AdminUserRead,
    AdminUserUpdate,
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
    RoleChangeRequest,
    SchoolCreate,
    SchoolRead,
    SchoolUpdate,
    TemporaryPasswordRead,
)
from app.modules.admin.service import (
    DepartmentNameTakenError,
    DepartmentNotFoundError,
    InvalidCoordinatorScopeError,
    InvalidDepartmentError,
    SchoolNameTakenError,
    SchoolNotFoundError,
    UserNotFoundError,
    change_role,
    create_department,
    create_school,
    delete_department,
    delete_school,
    get_department_or_raise,
    get_school_or_raise,
    get_user_or_raise,
    list_departments,
    list_schools,
    list_users,
    reset_temporary_password,
    set_active,
    update_department,
    update_school,
    update_user,
)
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/users", tags=["admin"])
org_router = APIRouter(tags=["admin"])
# Read-only school/department lists for every signed-in user: the directory
# filters need them, and the names are not sensitive. Mounted at /api/v1,
# not under /admin.
public_org_router = APIRouter(tags=["organisation"])


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


@router.patch("/{user_id}", response_model=AdminUserRead)
def patch_user(
    user_id: uuid.UUID,
    data: AdminUserUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_permission(Permission.USER_UPDATE))],
) -> User:
    target = _load_target(db, user_id)
    try:
        return update_user(db, actor, target, data, ip=client_ip(request))
    except InvalidCoordinatorScopeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="coordinator_scope_id does not name a real department.",
        ) from exc
    except InvalidDepartmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="department_id does not name a real department.",
        ) from exc


@router.post("/{user_id}/temporary-password", response_model=TemporaryPasswordRead)
def reset_user_password(
    user_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_permission(Permission.USER_UPDATE))],
) -> TemporaryPasswordRead:
    """Hand out a new temporary password when the first one was lost."""
    target = _load_target(db, user_id)
    try:
        user, temporary_password = reset_temporary_password(
            db, actor, target, ip=client_ip(request)
        )
    except SelfPasswordResetError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Change your own password from your account page instead.",
        ) from exc
    return TemporaryPasswordRead(
        user=AdminUserRead.model_validate(user), temporary_password=temporary_password
    )


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


@org_router.get(
    "/schools",
    response_model=list[SchoolRead],
    dependencies=[Depends(require_permission(Permission.SCHOOL_MANAGE))],
)
def read_schools(db: Annotated[Session, Depends(get_db)]) -> list[School]:
    return list_schools(db)


@org_router.post(
    "/schools",
    response_model=SchoolRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.SCHOOL_MANAGE))],
)
def create_school_route(data: SchoolCreate, db: Annotated[Session, Depends(get_db)]) -> School:
    try:
        return create_school(db, data)
    except SchoolNameTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A school with this name already exists."
        ) from exc


@org_router.patch(
    "/schools/{school_id}",
    response_model=SchoolRead,
    dependencies=[Depends(require_permission(Permission.SCHOOL_MANAGE))],
)
def patch_school(
    school_id: uuid.UUID, data: SchoolUpdate, db: Annotated[Session, Depends(get_db)]
) -> School:
    school = _load_school(db, school_id)
    try:
        return update_school(db, school, data)
    except SchoolNameTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A school with this name already exists."
        ) from exc


@org_router.delete(
    "/schools/{school_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission(Permission.SCHOOL_MANAGE))],
)
def delete_school_route(school_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> None:
    school = _load_school(db, school_id)
    delete_school(db, school)


@org_router.get(
    "/departments",
    response_model=list[DepartmentRead],
    dependencies=[Depends(require_permission(Permission.DEPARTMENT_MANAGE))],
)
def read_departments(
    db: Annotated[Session, Depends(get_db)], school_id: uuid.UUID | None = None
) -> list[Department]:
    return list_departments(db, school_id=school_id)


@org_router.post(
    "/departments",
    response_model=DepartmentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.DEPARTMENT_MANAGE))],
)
def create_department_route(
    data: DepartmentCreate, db: Annotated[Session, Depends(get_db)]
) -> Department:
    try:
        return create_department(db, data)
    except SchoolNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="School not found."
        ) from exc
    except DepartmentNameTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A department with this name already exists in that school.",
        ) from exc


@org_router.patch(
    "/departments/{department_id}",
    response_model=DepartmentRead,
    dependencies=[Depends(require_permission(Permission.DEPARTMENT_MANAGE))],
)
def patch_department(
    department_id: uuid.UUID, data: DepartmentUpdate, db: Annotated[Session, Depends(get_db)]
) -> Department:
    department = _load_department(db, department_id)
    try:
        return update_department(db, department, data)
    except DepartmentNameTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A department with this name already exists in that school.",
        ) from exc


@org_router.delete(
    "/departments/{department_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission(Permission.DEPARTMENT_MANAGE))],
)
def delete_department_route(
    department_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]
) -> None:
    department = _load_department(db, department_id)
    delete_department(db, department)


def _load_school(db: Annotated[Session, Depends(get_db)], school_id: uuid.UUID) -> School:
    try:
        return get_school_or_raise(db, school_id)
    except SchoolNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="School not found."
        ) from exc


def _load_department(
    db: Annotated[Session, Depends(get_db)], department_id: uuid.UUID
) -> Department:
    try:
        return get_department_or_raise(db, department_id)
    except DepartmentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Department not found."
        ) from exc


@public_org_router.get(
    "/schools", response_model=list[SchoolRead], dependencies=[Depends(get_current_user)]
)
def read_public_schools(db: Annotated[Session, Depends(get_db)]) -> list[School]:
    return list_schools(db)


@public_org_router.get(
    "/departments", response_model=list[DepartmentRead], dependencies=[Depends(get_current_user)]
)
def read_public_departments(
    db: Annotated[Session, Depends(get_db)], school_id: uuid.UUID | None = None
) -> list[Department]:
    return list_departments(db, school_id=school_id)
