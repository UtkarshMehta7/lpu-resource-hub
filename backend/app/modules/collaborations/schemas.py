"""Pydantic schemas for collaboration requests. sender_id comes from the
token and status only changes through accept/decline/cancel."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.modules.collaborations.models import CollaborationState, CollaborationStatus
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


class CollaborationSummary(BaseModel):
    """Where two people stand, for the control that offers to change it.

    The interface asks this once and renders the right thing, instead of
    offering to start a collaboration that is already running (ADR 0023).
    """

    state: CollaborationState
    #: The request awaiting an answer, when the state is REQUESTED.
    request_id: uuid.UUID | None = None
    #: Whether the viewer is the one waiting for an answer, or the one who
    #: owes it. None when nothing is pending.
    i_sent_it: bool | None = None
    #: Where to talk, once there is somewhere.
    conversation_id: uuid.UUID | None = None
