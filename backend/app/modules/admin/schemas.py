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

    There is deliberately no `role` field. The role of the new account is
    derived from the creator's own role (admin -> coordinator -> faculty ->
    student), so a request cannot ask for a role at all, let alone a higher
    one. `department_id` is only read from an admin appointing a coordinator;
    everyone else works in their own department and a value they don't own is
    rejected rather than quietly ignored.
    """

    registration_number: str = Field(pattern=REGISTRATION_NUMBER_PATTERN)
    full_name: str = Field(min_length=1, max_length=200)
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
    department_id: uuid.UUID | None
    # Who provisioned this account; null for the bootstrap admin.
    created_by: uuid.UUID | None
    coordinator_scope_type: CoordinatorScopeType | None
    coordinator_scope_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class AdminUserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    # Someone who self-registered has no department, which leaves them unable
    # to do anything department-scoped. An admin places them here; an explicit
    # null clears it again.
    department_id: uuid.UUID | None = None
    coordinator_scope_type: CoordinatorScopeType | None = None
    coordinator_scope_id: uuid.UUID | None = None


class TemporaryPasswordRead(BaseModel):
    """The one and only time a reset password is readable."""

    user: AdminUserRead
    temporary_password: str


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
