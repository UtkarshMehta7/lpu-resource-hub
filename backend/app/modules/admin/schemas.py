"""Pydantic schemas for admin user management.

Separate from users.schemas.UserRead (the self-facing profile schema) since
this exposes admin-only fields. role and is_active are deliberately absent
from AdminUserUpdate: they are never mass-assignable, only settable through
the dedicated /role, /activate and /deactivate action endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.users.models import CoordinatorScopeType, UserRole


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    coordinator_scope_type: CoordinatorScopeType | None
    coordinator_scope_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class AdminUserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    coordinator_scope_type: CoordinatorScopeType | None = None
    coordinator_scope_id: uuid.UUID | None = None


class RoleChangeRequest(BaseModel):
    role: UserRole
