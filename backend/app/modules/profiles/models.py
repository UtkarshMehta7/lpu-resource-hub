"""Student/researcher profiles and their skill/research-area attributes."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    program: Mapped[str] = mapped_column(String(150), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    interests: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_discoverable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ResearcherAvailability(StrEnum):
    AVAILABLE = "available"
    LIMITED = "limited"
    UNAVAILABLE = "unavailable"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class ResearcherProfile(Base):
    __tablename__ = "researcher_profiles"
    __table_args__ = (
        Index(
            "ix_researcher_profiles_search_document",
            "search_document",
            postgresql_using="gin",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    designation: Mapped[str] = mapped_column(String(150), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    availability: Mapped[ResearcherAvailability] = mapped_column(
        Enum(
            ResearcherAvailability,
            name="researcher_availability",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        server_default=ResearcherAvailability.AVAILABLE.value,
    )
    # List of {"label": str, "url": str}, validated in the Pydantic schema.
    links: Mapped[list[dict[str, str]] | None] = mapped_column(JSONB, nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(
            VerificationStatus,
            name="verification_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        server_default=VerificationStatus.UNVERIFIED.value,
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Weighted full-text document (A: name, B: designation + skills + research
    # areas, C: bio). Not a generated column: the inputs live in users,
    # user_skills and user_research_areas, and a generated column can only
    # read its own row. Recomputed by profiles.service whenever any input
    # changes -- see ADR 0005.
    search_document: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class UserSkill(Base):
    __tablename__ = "user_skills"
    __table_args__ = (CheckConstraint("proficiency BETWEEN 1 AND 5", name="ck_proficiency_range"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    proficiency: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class UserResearchArea(Base):
    __tablename__ = "user_research_areas"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    research_area_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_areas.id", ondelete="CASCADE"), primary_key=True
    )
    is_expertise: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
