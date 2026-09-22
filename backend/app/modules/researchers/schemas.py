"""Pydantic schemas for researcher verification."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.profiles.models import VerificationStatus


class VerificationQueueItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    full_name: str
    email: str
    designation: str
    department_id: uuid.UUID | None
    verification_status: VerificationStatus
    created_at: datetime


class VerifyDecisionRequest(BaseModel):
    decision: Literal["verified", "rejected"]
    comment: str | None = Field(default=None, max_length=2000)
