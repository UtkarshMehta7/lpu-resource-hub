"""Pydantic schemas for research projects.

owner_id, department_id and status are never client-writable: the owner and
department come from the caller, and status only changes through the
explicit action endpoints (/submit, /review, /complete, /archive).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.modules.projects.models import ProjectStatus


class _DateRange(BaseModel):
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def _start_before_end(self) -> Self:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


class ProjectCreate(_DateRange):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=20000)
    objectives: str | None = Field(default=None, max_length=10000)
    skill_ids: list[uuid.UUID] = Field(default_factory=list)
    research_area_ids: list[uuid.UUID] = Field(default_factory=list)


class ProjectUpdate(_DateRange):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, min_length=1, max_length=20000)
    objectives: str | None = Field(default=None, max_length=10000)
    skill_ids: list[uuid.UUID] | None = None
    research_area_ids: list[uuid.UUID] | None = None


class ReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _comment_required_on_reject(self) -> Self:
        if self.decision == "reject" and not (self.comment and self.comment.strip()):
            raise ValueError("a comment is required when rejecting")
        return self


class MemberCreate(BaseModel):
    user_id: uuid.UUID
    member_role: str = Field(min_length=1, max_length=100)


class MemberRead(BaseModel):
    user_id: uuid.UUID
    full_name: str
    registration_number: str
    member_role: str


class ProjectCard(BaseModel):
    id: uuid.UUID
    title: str
    summary: str
    status: ProjectStatus
    owner_id: uuid.UUID
    owner_name: str
    owner_registration_number: str
    department_id: uuid.UUID | None
    start_date: date | None
    end_date: date | None
    research_areas: list[str]
    skills: list[str]


class ProjectRead(ProjectCard):
    description: str
    objectives: str | None
    review_comment: str | None
    reviewed_at: datetime | None
    members: list[MemberRead]
    created_at: datetime
    updated_at: datetime
