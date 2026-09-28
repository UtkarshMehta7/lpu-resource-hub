"""Pydantic schemas for milestones.

`status`, `completed_at`, `completed_by` and `project_id` are never
client-writable: the project comes from the path, completion comes from the
status action, and the status itself only changes through /status so that
every change is checked against the transition table.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.milestones.models import MilestoneStatus
from app.modules.milestones.risk import Risk


class MilestoneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    due_date: date
    #: Appended to the end of the project's list when omitted.
    position: int | None = Field(default=None, ge=1, le=500)


class MilestoneUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    due_date: date | None = None
    position: int | None = Field(default=None, ge=1, le=500)


class StatusChangeRequest(BaseModel):
    status: MilestoneStatus


class DependencyCreate(BaseModel):
    depends_on_id: uuid.UUID


class MilestoneLink(BaseModel):
    """A milestone referred to from somewhere else, without its whole shape."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    due_date: date
    status: MilestoneStatus


class MilestoneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    due_date: date
    status: MilestoneStatus
    position: int
    completed_at: datetime | None
    completed_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    # Derived per request, never stored -- see milestones/risk.py.
    risk: Risk
    days_until_due: int
    depends_on: list[MilestoneLink] = Field(default_factory=list)
    #: The subset of `depends_on` that is actually holding this one up.
    blocked_by: list[MilestoneLink] = Field(default_factory=list)


class MyMilestone(MilestoneRead):
    """One of the caller's milestones, with enough context to act on it."""

    project_title: str


class AtRiskMilestone(MilestoneLink):
    risk: Risk
    days_until_due: int


class AtRiskProject(BaseModel):
    project_id: uuid.UUID
    title: str
    owner_id: uuid.UUID
    owner_name: str
    owner_registration_number: str
    department_id: uuid.UUID | None
    overdue_count: int
    at_risk_count: int
    blocked_count: int
    #: Soonest-due first, so the board leads with what is most urgent.
    milestones: list[AtRiskMilestone]


__all__ = [
    "AtRiskMilestone",
    "AtRiskProject",
    "DependencyCreate",
    "MilestoneCreate",
    "MilestoneLink",
    "MilestoneRead",
    "MilestoneUpdate",
    "MyMilestone",
    "StatusChangeRequest",
]
