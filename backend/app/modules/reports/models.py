"""User reports about content, and their moderation state."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReportTargetType(StrEnum):
    PROJECT = "project"
    OPPORTUNITY = "opportunity"
    PUBLICATION = "publication"
    PROFILE = "profile"


class ReportStatus(StrEnum):
    OPEN = "open"
    DISMISSED = "dismissed"
    ACTIONED = "actioned"


class ContentReport(Base):
    __tablename__ = "content_reports"
    __table_args__ = (
        # One open report per person per thing; they can report it again
        # once the first one has been dealt with.
        Index(
            "uq_content_reports_open",
            "reporter_id",
            "target_type",
            "target_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Polymorphic on purpose: a report can point at any kind of content, so
    # there is no single table to reference. The service checks the target
    # exists and is visible to the reporter before the row is written.
    target_type: Mapped[ReportTargetType] = mapped_column(
        Enum(
            ReportTargetType,
            name="report_target_type",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(
            ReportStatus,
            name="report_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        server_default=ReportStatus.OPEN.value,
        index=True,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
