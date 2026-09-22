"""Direct collaboration requests between users."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CollaborationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CANCELLED = "cancelled"


class CollaborationRequest(Base):
    __tablename__ = "collaboration_requests"
    __table_args__ = (
        CheckConstraint("sender_id <> recipient_id", name="not_self"),
        # At most one PENDING request per sender/recipient/project. NULLS NOT
        # DISTINCT makes "no project" count as one value, so two pending
        # project-less requests to the same person also collide.
        Index(
            "uq_collaboration_requests_pending",
            "sender_id",
            "recipient_id",
            "project_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CollaborationStatus] = mapped_column(
        Enum(
            CollaborationStatus,
            name="collaboration_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        server_default=CollaborationStatus.PENDING.value,
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
