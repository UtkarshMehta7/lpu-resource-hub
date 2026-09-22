"""Pydantic schemas for opportunities.

status, created_by and department_id are never client-writable: status only
moves through the action endpoints, and the department comes from the
project (or the coordinator's scope).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.modules.opportunities.models import OpportunityStatus, OpportunityType


class SkillRequirement(BaseModel):
    skill_id: uuid.UUID
    is_required: bool = True


class OpportunityCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=20000)
    opportunity_type: OpportunityType
    project_id: uuid.UUID | None = None
    eligibility: str | None = Field(default=None, max_length=5000)
    positions: int = Field(ge=1, le=100)
    deadline: date
    skills: list[SkillRequirement] = Field(default_factory=list, max_length=30)


class OpportunityUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=20000)
    opportunity_type: OpportunityType | None = None
    eligibility: str | None = Field(default=None, max_length=5000)
    positions: int | None = Field(default=None, ge=1, le=100)
    deadline: date | None = None
    skills: list[SkillRequirement] | None = Field(default=None, max_length=30)


class SkillTag(BaseModel):
    id: uuid.UUID
    name: str
    is_required: bool


class OpportunityCard(BaseModel):
    id: uuid.UUID
    title: str
    opportunity_type: OpportunityType
    status: OpportunityStatus
    project_id: uuid.UUID | None
    project_title: str | None
    department_id: uuid.UUID | None
    created_by: uuid.UUID
    creator_name: str
    positions: int
    accepted_count: int
    deadline: date
    skills: list[SkillTag]


class OpportunityRead(OpportunityCard):
    description: str
    eligibility: str | None
    created_at: datetime
    updated_at: datetime
    # The viewer's own application, if they have one -- lets the UI show
    # "Applied" instead of the apply form without a second request.
    my_application_id: uuid.UUID | None
