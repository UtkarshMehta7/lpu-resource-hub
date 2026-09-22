"""Funding calls and the research areas they target."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FundingStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class FundingOpportunity(Base):
    __tablename__ = "funding_opportunities"
    __table_args__ = (
        CheckConstraint(
            "amount_min IS NULL OR amount_max IS NULL OR amount_min <= amount_max",
            name="amount_range_ordered",
        ),
        CheckConstraint("amount_min IS NULL OR amount_min >= 0", name="amount_min_not_negative"),
        Index("ix_funding_search_document", "search_document", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    eligibility: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Either a free-text amount ("up to two lakh rupees") or a numeric range.
    amount_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deadline: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    official_source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[FundingStatus] = mapped_column(
        Enum(
            FundingStatus,
            name="funding_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        server_default=FundingStatus.OPEN.value,
        index=True,
    )
    # Seeded calls are fictional and say so; nothing here is a real call.
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    search_document: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(organization, '')), 'B') || "
            "setweight(to_tsvector('english', coalesce(description, '')), 'C') || "
            "setweight(to_tsvector('english', coalesce(eligibility, '')), 'D')",
            persisted=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class FundingResearchArea(Base):
    __tablename__ = "funding_research_areas"

    funding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("funding_opportunities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    research_area_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_areas.id", ondelete="CASCADE"), primary_key=True
    )
