"""Request/response schemas for the auth module."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import MIN_PASSWORD_LENGTH, is_common_password
from app.modules.users.schemas import UserRead

# Students no longer self-register: their department creates the account
# (see docs/adr/0015). Faculty still register themselves and are then
# verified by a coordinator.
SelfRegisterableRole = Literal["faculty"]

REGISTRATION_NUMBER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{3,49}$"


def normalise_registration_number(value: str) -> str:
    """Upper-cased and trimmed, so 'demo000001' and 'DEMO000001' are one account."""
    return value.strip().upper()


def _validate_new_password(value: str) -> str:
    if is_common_password(value):
        raise ValueError("This password is too common. Choose a different one.")
    return value


class RegisterRequest(BaseModel):
    """Faculty self-registration. The registration number is what they log in
    with; email is optional contact information."""

    registration_number: str = Field(pattern=REGISTRATION_NUMBER_PATTERN)
    email: EmailStr | None = None
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

    @field_validator("registration_number")
    @classmethod
    def _normalise_registration_number(cls, value: str) -> str:
        return normalise_registration_number(value)


class LoginRequest(BaseModel):
    registration_number: str = Field(min_length=1, max_length=50)
    password: str

    @field_validator("registration_number")
    @classmethod
    def _normalise_registration_number(cls, value: str) -> str:
        return normalise_registration_number(value)


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
