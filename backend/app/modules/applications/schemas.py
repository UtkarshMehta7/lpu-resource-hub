"""Pydantic schemas for applications. status is only ever changed through
the /status and /withdraw actions; applicant_id comes from the token."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.applications.models import ApplicationStatus
from app.modules.opportunities.models import OpportunityType


class ApplicationCreate(BaseModel):
    statement: str = Field(min_length=1, max_length=5000)


class StatusChangeRequest(BaseModel):
    status: ApplicationStatus
    note: str | None = Field(default=None, max_length=2000)
    # On ACCEPTED, also add the applicant to the opportunity's project team.
    add_to_project: bool = False


class WithdrawRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class ApplicationEventRead(BaseModel):
    status: ApplicationStatus
    note: str | None
    created_at: datetime


class ApplicationRead(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID
    opportunity_title: str
    opportunity_type: OpportunityType
    applicant_id: uuid.UUID
    applicant_name: str
    statement: str
    status: ApplicationStatus
    note: str | None
    decided_at: datetime | None
    created_at: datetime
    events: list[ApplicationEventRead]
