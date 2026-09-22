"""Request/response schemas for the auth module."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import MIN_PASSWORD_LENGTH, is_common_password
from app.modules.users.schemas import UserRead

SelfRegisterableRole = Literal["student", "faculty"]


def _validate_new_password(value: str) -> str:
    if is_common_password(value):
        raise ValueError("This password is too common. Choose a different one.")
    return value


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    role: SelfRegisterableRole

    @field_validator("full_name")
    @classmethod
    def _strip_full_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("full_name must not be blank")
        return stripped

    @field_validator("password")
    @classmethod
    def _reject_common_password(cls, value: str) -> str:
        return _validate_new_password(value)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _reject_common_password(cls, value: str) -> str:
        return _validate_new_password(value)


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserRead
