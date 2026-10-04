"""Suspected duplicate publications, and what was decided about each pair.

Duplicates get *into* the database in ways the import path cannot prevent:
two researchers each add the same paper by hand, or a title-only record is
later matched by one carrying a DOI. The import de-duplicates what it brings
in (ADR 0025); this is for what is already stored.

A merge **snapshots and deletes** the losing record rather than leaving a
tombstone behind. Publications are read in fifteen places across eight
modules -- listings, search, analytics, recommendations, reports -- and a
hidden-row flag would have to be honoured by every one of them. One missed
query is a ghost publication that still counts in a figure or still answers a
search. A deleted row cannot be missed, and the snapshot is what makes the
merge reversible anyway.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DuplicateStatus(StrEnum):
    #: Found by a scan, nobody has looked yet.
    SUSPECTED = "suspected"
    #: One record absorbed the other. Reversible from `snapshot`.
    MERGED = "merged"
    #: Looked at, and they are genuinely different works.
    SEPARATE = "separate"
    #: Cannot tell, or not now. Stays out of the queue without claiming a
    #: judgement that was never made.
    IGNORED = "ignored"


class PublicationDuplicate(Base):
    __tablename__ = "publication_duplicates"
    __table_args__ = (
        # A pair is a pair, so a duplicate review row is impossible in the
        # database rather than guarded in a service somebody can forget --
        # the same reasoning as `collaborations` (ADR 0023). NULLs are
        # distinct in a unique constraint, which is what lets a decided row
        # keep its place after its publication is gone.
        UniqueConstraint(
            "publication_a_id", "publication_b_id", name="uq_publication_duplicate_pair"
        ),
        CheckConstraint(
            "publication_a_id IS NULL"
            " OR publication_b_id IS NULL"
            " OR publication_a_id < publication_b_id",
            name="ck_publication_duplicate_ordered",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    #: Ordered so (a, b) and (b, a) are the same row. Nullable because a
    #: merge deletes one of them and an outright deletion may remove either,
    #: and the decision still has to be readable afterwards.
    publication_a_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("publications.id", ondelete="SET NULL"), nullable=True
    )
    publication_b_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("publications.id", ondelete="SET NULL"), nullable=True
    )
    #: Title similarity, 0-100, from the same function the importer uses.
    score: Mapped[float] = mapped_column(Float, nullable=False)
    #: Why this pair was suggested, so a reviewer can judge without opening
    #: both records: matching year, shared authors, venue, DOI presence.
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[DuplicateStatus] = mapped_column(
        Enum(
            DuplicateStatus,
            name="duplicate_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        server_default=DuplicateStatus.SUSPECTED.value,
        index=True,
    )
    #: Which record survived a merge.
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("publications.id", ondelete="SET NULL"), nullable=True
    )
    #: The deleted record in full, with its authors and project links, so the
    #: merge can be undone. Written only on a merge.
    snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
