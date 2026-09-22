"""Schemas for content reports. status/reviewed_by are never client-writable."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.reports.models import ReportStatus, ReportTargetType


class ReportCreate(BaseModel):
    target_type: ReportTargetType
    target_id: uuid.UUID
    reason: str = Field(min_length=10, max_length=2000)


class ReportResolve(BaseModel):
    # OPEN isn't a resolution, so it can't be requested here.
    status: Literal[ReportStatus.DISMISSED, ReportStatus.ACTIONED]
    note: str | None = Field(default=None, max_length=2000)


class ReportRead(BaseModel):
    id: uuid.UUID
    reporter_id: uuid.UUID
    reporter_name: str
    target_type: ReportTargetType
    target_id: uuid.UUID
    target_title: str | None
    reason: str
    status: ReportStatus
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    resolution_note: str | None
    created_at: datetime
