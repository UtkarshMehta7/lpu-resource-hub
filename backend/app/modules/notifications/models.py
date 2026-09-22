"""In-app notifications."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationType(StrEnum):
    APPLICATION_RECEIVED = "application_received"
    APPLICATION_DECIDED = "application_decided"
    COLLABORATION_REQUEST = "collaboration_request"
    COLLABORATION_RESPONSE = "collaboration_response"
    BOOKING_DECIDED = "booking_decided"
    PROJECT_REVIEWED = "project_reviewed"
    PROFILE_VERIFIED = "profile_verified"
    RELEVANT_OPPORTUNITY = "relevant_opportunity"
    DEADLINE_REMINDER = "deadline_reminder"


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_unread", "user_id", "read_at"),
        # One reminder per user per thing per lead time: the deadline job can
        # run as often as it likes without ever notifying twice.
        Index(
            "uq_notifications_dedupe_key",
            "user_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(
            NotificationType,
            name="notification_type",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    # Everything the UI needs to render and link the notification, so reading
    # the list never fans out into per-row lookups.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    # Only set for notifications that must not repeat (reminders, matches);
    # the partial unique index above makes re-sending a no-op.
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
