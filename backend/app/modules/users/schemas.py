"""Pydantic schemas for the users module. No ORM objects cross this boundary."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.modules.users.models import CoordinatorScopeType, UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    department_id: uuid.UUID | None
    coordinator_scope_type: CoordinatorScopeType | None
    coordinator_scope_id: uuid.UUID | None
    onboarding_complete: bool
    created_at: datetime
