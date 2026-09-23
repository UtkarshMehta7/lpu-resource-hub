"""Request/response schemas for the auth module."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.security import MIN_PASSWORD_LENGTH, is_common_password
from app.modules.users.schemas import UserRead

# Nobody self-registers: accounts are provisioned down the institutional
# hierarchy (ADR 0019), so there is no registration request schema here.
REGISTRATION_NUMBER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{3,49}$"


def normalise_registration_number(value: str) -> str:
    """Upper-cased and trimmed, so 'demo000001' and 'DEMO000001' are one account."""
    return value.strip().upper()


def _validate_new_password(value: str) -> str:
    if is_common_password(value):
        raise ValueError("This password is too common. Choose a different one.")
    return value


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
