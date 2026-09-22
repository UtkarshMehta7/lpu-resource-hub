"""Notification schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.modules.notifications.models import NotificationType


class NotificationRead(BaseModel):
    id: uuid.UUID
    notification_type: NotificationType
    # Everything needed to render and link the row, captured when it was made.
    payload: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class NotificationList(BaseModel):
    unread_count: int
    items: list[NotificationRead]
