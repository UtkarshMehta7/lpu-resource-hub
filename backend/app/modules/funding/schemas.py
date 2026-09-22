"""Funding call schemas. is_demo and created_by are never client-writable."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.funding.models import FundingStatus


class FundingCreate(BaseModel):
    organization: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=20000)
    eligibility: str | None = Field(default=None, max_length=10000)
    amount_text: str | None = Field(default=None, max_length=200)
    amount_min: int | None = Field(default=None, ge=0)
    amount_max: int | None = Field(default=None, ge=0)
    deadline: date
    official_source_url: str | None = Field(default=None, max_length=2000)
    research_area_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)

    @field_validator("official_source_url")
    @classmethod
    def _check_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("http://", "https://")):
            raise ValueError("official_source_url must start with http:// or https://")
        return value

    @model_validator(mode="after")
    def _amounts_ordered(self) -> Self:
        if (
            self.amount_min is not None
            and self.amount_max is not None
            and self.amount_min > self.amount_max
        ):
            raise ValueError("amount_min must be less than or equal to amount_max")
        return self


class FundingUpdate(BaseModel):
    organization: str | None = Field(default=None, min_length=1, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, min_length=1, max_length=20000)
    eligibility: str | None = Field(default=None, max_length=10000)
    amount_text: str | None = Field(default=None, max_length=200)
    amount_min: int | None = Field(default=None, ge=0)
    amount_max: int | None = Field(default=None, ge=0)
    deadline: date | None = None
    official_source_url: str | None = Field(default=None, max_length=2000)
    status: FundingStatus | None = None
    research_area_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)


class FundingRead(BaseModel):
    id: uuid.UUID
    organization: str
    title: str
    description: str
    eligibility: str | None
    amount_text: str | None
    amount_min: int | None
    amount_max: int | None
    deadline: date
    official_source_url: str | None
    status: FundingStatus
    is_demo: bool
    research_areas: list[str]
    created_at: datetime
