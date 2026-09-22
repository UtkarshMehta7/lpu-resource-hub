"""Pydantic schemas for the taxonomy module."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.taxonomy.models import TagSuggestionStatus, TagSuggestionType


class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)


class ResearchAreaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    created_at: datetime


class ResearchAreaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    parent_id: uuid.UUID | None = None


class TagAliasRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alias: str
    skill_id: uuid.UUID | None
    research_area_id: uuid.UUID | None
    created_at: datetime


class TagAliasCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=150)
    skill_id: uuid.UUID | None = None
    research_area_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _exactly_one_target(self) -> Self:
        if (self.skill_id is None) == (self.research_area_id is None):
            raise ValueError("exactly one of skill_id or research_area_id must be set")
        return self


class TagSuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    suggested_name: str
    suggested_type: TagSuggestionType
    suggested_by: uuid.UUID
    status: TagSuggestionStatus
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime


class TagSuggestionCreate(BaseModel):
    suggested_name: str = Field(min_length=1, max_length=150)
    suggested_type: TagSuggestionType
