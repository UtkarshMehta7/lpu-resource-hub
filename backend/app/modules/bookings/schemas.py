"""Booking schemas. status and decided_by are never client-writable."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.modules.bookings.models import BookingStatus


class BookingCreate(BaseModel):
    equipment_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    purpose: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        return self


class BookingDecision(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class BookingRead(BaseModel):
    id: uuid.UUID
    equipment_id: uuid.UUID
    equipment_name: str
    facility_name: str
    user_id: uuid.UUID
    user_name: str
    starts_at: datetime
    ends_at: datetime
    purpose: str
    status: BookingStatus
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime


class BusySlot(BaseModel):
    """An approved booking, as seen by someone checking availability.

    Only the period is public: who booked it is not, unless it's yours.
    """

    starts_at: datetime
    ends_at: datetime
    is_mine: bool


class AvailabilityRead(BaseModel):
    equipment_id: uuid.UUID
    maintenance_status: str
    students_allowed: bool
    requires_approval: bool
    max_hours: int
    min_lead_hours: int
    busy: list[BusySlot]
