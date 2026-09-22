"""Publications, their ordered author lists and links to projects."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

MIN_YEAR = 1900
MAX_YEAR = 2100


class PublicationType(StrEnum):
    JOURNAL_ARTICLE = "journal_article"
    CONFERENCE_PAPER = "conference_paper"
    BOOK_CHAPTER = "book_chapter"
    BOOK = "book"
    PREPRINT = "preprint"
    THESIS = "thesis"
    OTHER = "other"


class Publication(Base):
    __tablename__ = "publications"
    __table_args__ = (
        CheckConstraint(f"year BETWEEN {MIN_YEAR} AND {MAX_YEAR}", name="year_in_range"),
        Index("ix_publications_search_document", "search_document", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(300), nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # Stored lower-cased so "10.1/ABC" and "10.1/abc" collide as they should.
    doi: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    pub_type: Mapped[PublicationType] = mapped_column(
        Enum(
            PublicationType,
            name="publication_type",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    search_document: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(abstract, '')), 'B') || "
            "setweight(to_tsvector('english', coalesce(venue, '')), 'C')",
            persisted=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PublicationAuthor(Base):
    """One author slot: a platform user, or an external name -- never both."""

    __tablename__ = "publication_authors"
    __table_args__ = (
        CheckConstraint("num_nonnulls(user_id, external_name) = 1", name="exactly_one_author"),
        CheckConstraint("author_order >= 1", name="author_order_positive"),
        UniqueConstraint("publication_id", "author_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    publication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SET NULL would violate the CHECK, so deleting a user deletes their
    # author slot; the rest of the author list keeps its order.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    external_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    author_order: Mapped[int] = mapped_column(Integer, nullable=False)


class ProjectPublication(Base):
    __tablename__ = "project_publications"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    publication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("publications.id", ondelete="CASCADE"), primary_key=True
    )
