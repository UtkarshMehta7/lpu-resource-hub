"""Facility and equipment endpoints, mounted under /api/v1.

The catalogue is readable by every signed-in user; managing it needs
facility:manage, and a coordinator's writes are confined to the department
they oversee (403 outside it -- the facility is public, so hiding it would
be pointless).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.pagination import Page, PageParams
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import enforce_search_rate_limit
from app.db.session import get_db
from app.modules.facilities import service
from app.modules.facilities.policies import OutOfScopeError
from app.modules.facilities.schemas import (
    EquipmentCreate,
    EquipmentRead,
    EquipmentUpdate,
    FacilityCreate,
    FacilityRead,
    FacilityUpdate,
)
from app.modules.users.models import User

router = APIRouter(tags=["facilities"])

CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
Manager = Annotated[User, Depends(require_permission(Permission.FACILITY_MANAGE))]

_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    service.FacilityNotFoundError: (status.HTTP_404_NOT_FOUND, "Facility not found."),
    service.EquipmentNotFoundError: (status.HTTP_404_NOT_FOUND, "Equipment not found."),
    OutOfScopeError: (
        status.HTTP_403_FORBIDDEN,
        "You can only manage facilities in your own department.",
    ),
    service.DepartmentRequiredError: (
        status.HTTP_403_FORBIDDEN,
        "You can only create facilities in the department you oversee.",
    ),
    service.DuplicateFacilityError: (
        status.HTTP_409_CONFLICT,
        "That department already has a facility with this name.",
    ),
}


@contextmanager
def _domain_errors() -> Iterator[None]:
    try:
        yield
    except tuple(_ERROR_MAP) as exc:
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from exc


@router.get(
    "/facilities",
    response_model=Page[FacilityRead],
    dependencies=[Depends(get_current_user), Depends(enforce_search_rate_limit)],
)
def read_facilities(
    db: DbSession,
    params: Annotated[PageParams, Depends()],
    q: str | None = None,
    department_id: uuid.UUID | None = None,
) -> Page[FacilityRead]:
    return service.list_facilities(db, params, q=q, department_id=department_id)


@router.post("/facilities", response_model=FacilityRead, status_code=status.HTTP_201_CREATED)
def create_facility(data: FacilityCreate, db: DbSession, actor: Manager) -> FacilityRead:
    with _domain_errors():
        return service.create_facility(db, actor, data)


@router.get("/facilities/{facility_id}", response_model=FacilityRead)
def read_facility(facility_id: uuid.UUID, db: DbSession, viewer: CurrentUser) -> FacilityRead:
    with _domain_errors():
        return service.get_facility(db, facility_id)


@router.patch("/facilities/{facility_id}", response_model=FacilityRead)
def update_facility(
    facility_id: uuid.UUID, data: FacilityUpdate, db: DbSession, actor: Manager
) -> FacilityRead:
    with _domain_errors():
        return service.update_facility(db, actor, facility_id, data)


@router.delete("/facilities/{facility_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_facility(facility_id: uuid.UUID, db: DbSession, actor: Manager) -> None:
    with _domain_errors():
        service.delete_facility(db, actor, facility_id)


@router.get(
    "/equipment",
    response_model=Page[EquipmentRead],
    dependencies=[Depends(get_current_user), Depends(enforce_search_rate_limit)],
)
def read_equipment_list(
    db: DbSession,
    params: Annotated[PageParams, Depends()],
    facility_id: uuid.UUID | None = None,
    category: str | None = None,
    q: str | None = None,
) -> Page[EquipmentRead]:
    return service.list_equipment(db, params, facility_id=facility_id, category=category, q=q)


@router.post("/equipment", response_model=EquipmentRead, status_code=status.HTTP_201_CREATED)
def create_equipment(data: EquipmentCreate, db: DbSession, actor: Manager) -> EquipmentRead:
    with _domain_errors():
        return service.create_equipment(db, actor, data)


@router.get("/equipment/{equipment_id}", response_model=EquipmentRead)
def read_equipment(equipment_id: uuid.UUID, db: DbSession, viewer: CurrentUser) -> EquipmentRead:
    with _domain_errors():
        return service.get_equipment(db, equipment_id)


@router.patch("/equipment/{equipment_id}", response_model=EquipmentRead)
def update_equipment(
    equipment_id: uuid.UUID, data: EquipmentUpdate, db: DbSession, actor: Manager
) -> EquipmentRead:
    with _domain_errors():
        return service.update_equipment(db, actor, equipment_id, data)


@router.delete("/equipment/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_equipment(equipment_id: uuid.UUID, db: DbSession, actor: Manager) -> None:
    with _domain_errors():
        service.delete_equipment(db, actor, equipment_id)
