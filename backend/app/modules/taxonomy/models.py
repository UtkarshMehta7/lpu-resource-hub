"""Shared research taxonomy: skills, research areas, aliases, suggestions."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchArea(Base):
    __tablename__ = "research_areas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    # Two levels max, enforced in the service layer: a research_area whose
    # parent itself has a parent is rejected.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_areas.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TagAlias(Base):
    """alias -> canonical skill or research area. Exactly one target is set."""

    __tablename__ = "tag_aliases"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(skill_id, research_area_id) = 1", name="ck_exactly_one_target"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    alias: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    skill_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=True
    )
    research_area_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_areas.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TagSuggestionType(StrEnum):
    SKILL = "skill"
    RESEARCH_AREA = "research_area"


class TagSuggestionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TagSuggestion(Base):
    __tablename__ = "tag_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    suggested_name: Mapped[str] = mapped_column(String(150), nullable=False)
    suggested_type: Mapped[TagSuggestionType] = mapped_column(
        Enum(
            TagSuggestionType,
            name="tag_suggestion_type",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    suggested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[TagSuggestionStatus] = mapped_column(
        Enum(
            TagSuggestionStatus,
            name="tag_suggestion_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        server_default=TagSuggestionStatus.PENDING.value,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
