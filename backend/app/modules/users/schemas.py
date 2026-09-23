"""Pydantic schemas for the users module. No ORM objects cross this boundary."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.modules.users.models import CoordinatorScopeType, UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    registration_number: str
    # Optional contact address; never used to sign in.
    email: str | None
    full_name: str
    role: UserRole
    is_active: bool
    department_id: uuid.UUID | None
    coordinator_scope_type: CoordinatorScopeType | None
    coordinator_scope_id: uuid.UUID | None
    onboarding_complete: bool
    # True until the temporary password set by an admin/faculty is replaced.
    must_change_password: bool
    created_at: datetime
