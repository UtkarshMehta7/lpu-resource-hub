"""A record of every nudge, which is what makes the cooldown possible.

Without a row per nudge there is no way to know when the last one was sent,
and "remind them" becomes "let one person generate unlimited notifications
for somebody senior to them".
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NudgeKind(StrEnum):
    PROFILE_VERIFICATION = "profile_verification"
    PROJECT_REVIEW = "project_review"
    BOOKING_APPROVAL = "booking_approval"
    APPLICATION_DECISION = "application_decision"


class Nudge(Base):
    __tablename__ = "nudges"
    __table_args__ = (
        # The cooldown lookup: the most recent nudge from this person about
        # this thing.
        Index("ix_nudges_actor_kind_entity", "actor_id", "kind", "entity_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[NudgeKind] = mapped_column(
        Enum(
            NudgeKind,
            name="nudge_kind",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    #: The thing being waited on. Not a foreign key: it points at four
    #: different tables depending on the kind, and the service checks it.
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    #: How many people the nudge reached, for the actor's own feedback.
    recipient_count: Mapped[int] = mapped_column(nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


__all__ = ["Nudge", "NudgeKind"]
