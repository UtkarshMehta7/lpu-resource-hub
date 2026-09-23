"""Pydantic schemas for admin user management.

Separate from users.schemas.UserRead (the self-facing profile schema) since
this exposes admin-only fields. role and is_active are deliberately absent
from AdminUserUpdate: they are never mass-assignable, only settable through
the dedicated /role, /activate and /deactivate action endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.auth.schemas import REGISTRATION_NUMBER_PATTERN, normalise_registration_number
from app.modules.users.models import CoordinatorScopeType, UserRole


class AccountCreateRequest(BaseModel):
    """Create an account for someone else.

    Admins may pass any role; faculty and coordinators may only create
    students, and only in their own department (the API ignores a department
    they don't own rather than trusting it).
    """

    registration_number: str = Field(pattern=REGISTRATION_NUMBER_PATTERN)
    full_name: str = Field(min_length=1, max_length=200)
    role: UserRole = UserRole.STUDENT
    department_id: uuid.UUID | None = None
    email: EmailStr | None = None

    @field_validator("registration_number")
    @classmethod
    def _normalise(cls, value: str) -> str:
        return normalise_registration_number(value)

    @field_validator("full_name")
    @classmethod
    def _strip(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("full_name must not be blank")
        return stripped


class CreatedAccountRead(BaseModel):
    user: AdminUserRead
    # Shown once, so the creator can pass it on. It is never retrievable again.
    temporary_password: str


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    registration_number: str
    email: str | None
    full_name: str
    role: UserRole
    is_active: bool
    must_change_password: bool
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


class SchoolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class SchoolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class SchoolUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class DepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class DepartmentCreate(BaseModel):
    school_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


CreatedAccountRead.model_rebuild()
