"""Pydantic schemas for collaboration requests. sender_id comes from the
token and status only changes through accept/decline/cancel."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.modules.collaborations.models import CollaborationStatus
from app.modules.users.models import UserRole


class CollaborationCreate(BaseModel):
    recipient_id: uuid.UUID
    project_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=2000)


class Party(BaseModel):
    id: uuid.UUID
    full_name: str
    registration_number: str
    role: UserRole


class CollaborationRead(BaseModel):
    id: uuid.UUID
    sender: Party
    recipient: Party
    project_id: uuid.UUID | None
    project_title: str | None
    message: str
    status: CollaborationStatus
    responded_at: datetime | None
    created_at: datetime


class Box(StrEnum):
    INBOX = "inbox"
    SENT = "sent"
