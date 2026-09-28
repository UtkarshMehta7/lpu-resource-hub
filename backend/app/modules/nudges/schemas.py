"""Request and response shapes for nudges."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.modules.nudges.models import NudgeKind


class NudgeRequest(BaseModel):
    kind: NudgeKind
    entity_id: uuid.UUID


class NudgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: NudgeKind
    #: How many people were told, so the sender knows it went somewhere.
    recipients: int
    next_allowed_at: datetime


__all__ = ["NudgeRead", "NudgeRequest"]
