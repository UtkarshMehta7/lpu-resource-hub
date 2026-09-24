"""The collaboration relationship between two people, and the requests for it.

A collaboration belongs to a PAIR, not to a request. Keying it to a request
was the modelling mistake behind three separate bugs: you could request
somebody you already collaborated with, accepting that produced a second
conversation so the pair's history split in two, and A->B and B->A were
different rows so two people could hold pending requests to each other
(ADR 0023).

`collaborations` is therefore stored with the pair normalised -- user_a_id is
always the lesser uuid -- behind a unique constraint, so a duplicate is
impossible at the database level rather than dependent on a service check
somebody later forgets to write.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CollaborationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    #: The work finished, or the two decided to stop. Either party may end an
    #: accepted collaboration; the thread stays readable but takes no new
    #: messages.
    ENDED = "ended"


class CollaborationState(StrEnum):
    """Where a pair stands. Derived from their requests, stored so the
    interface can ask one question instead of reconstructing it."""

    #: Never collaborated, or the last request was declined or cancelled.
    NONE = "none"
    REQUESTED = "requested"
    ACTIVE = "active"
    ENDED = "ended"


class Collaboration(Base):
    """One row per unordered pair of people, for the life of the pair."""

    __tablename__ = "collaborations"
    __table_args__ = (
        # Normalised, so {a,b} and {b,a} are the same row and the unique
        # constraint below actually means "one relationship per pair".
        CheckConstraint("user_a_id < user_b_id", name="pair_is_ordered"),
        UniqueConstraint("user_a_id", "user_b_id", name="uq_collaborations_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    state: Mapped[CollaborationState] = mapped_column(
        Enum(
            CollaborationState,
            name="collaboration_state",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        server_default=CollaborationState.NONE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


def normalise_pair(one: uuid.UUID, other: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """The pair in the order the table stores it."""
    return (one, other) if one < other else (other, one)


class CollaborationRequest(Base):
    __tablename__ = "collaboration_requests"
    __table_args__ = (
        CheckConstraint("sender_id <> recipient_id", name="not_self"),
        # There used to be a partial unique index here allowing one PENDING
        # request per sender/recipient/project. It is gone, dropped by
        # migration 0021: duplicates are now prevented one level up, by the
        # unique constraint on the pair in `collaborations`. Keeping both
        # would mean two rules that can disagree -- the index counted a
        # direction and a project as distinct, which is exactly how two
        # people ended up with three live requests and two conversations.
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
    #: The relationship this request is an event in.
    collaboration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collaborations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
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
