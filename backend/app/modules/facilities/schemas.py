"""Schemas for the facility and equipment catalogue."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.facilities.models import MaintenanceStatus


class FacilityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    department_id: uuid.UUID | None = None
    location: str | None = Field(default=None, max_length=300)
    contact: str | None = Field(default=None, max_length=300)


class FacilityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    location: str | None = Field(default=None, max_length=300)
    contact: str | None = Field(default=None, max_length=300)


class FacilityRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    department_id: uuid.UUID | None
    location: str | None
    contact: str | None
    equipment_count: int
    created_at: datetime


class EquipmentCreate(BaseModel):
    facility_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = Field(default=None, max_length=150)
    maintenance_status: MaintenanceStatus = MaintenanceStatus.AVAILABLE
    students_allowed: bool = True
    requires_approval: bool = True
    max_hours: int = Field(default=8, ge=1, le=24 * 14)
    min_lead_hours: int = Field(default=0, ge=0, le=24 * 30)


class EquipmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = Field(default=None, max_length=150)
    maintenance_status: MaintenanceStatus | None = None
    students_allowed: bool | None = None
    requires_approval: bool | None = None
    max_hours: int | None = Field(default=None, ge=1, le=24 * 14)
    min_lead_hours: int | None = Field(default=None, ge=0, le=24 * 30)


class EquipmentRead(BaseModel):
    id: uuid.UUID
    facility_id: uuid.UUID
    facility_name: str
    department_id: uuid.UUID | None
    name: str
    description: str | None
    category: str | None
    maintenance_status: MaintenanceStatus
    students_allowed: bool
    requires_approval: bool
    max_hours: int
    min_lead_hours: int
    created_at: datetime
