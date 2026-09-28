"""Project milestones and the dependencies between them."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MilestoneStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


#: Neither of these is outstanding work, so neither can be late.
SETTLED_STATUSES = frozenset({MilestoneStatus.DONE, MilestoneStatus.CANCELLED})


class Milestone(Base):
    __tablename__ = "milestones"
    __table_args__ = (
        # Two milestones of one project never share a slot, so the list and
        # the timeline have a total order that does not depend on insertion.
        UniqueConstraint("project_id", "position", name="uq_milestones_project_position"),
        # "Done" without a completion date would make every report that counts
        # on-time delivery wrong, so the database refuses it outright.
        CheckConstraint("status <> 'done' OR completed_at IS NOT NULL", name="done_is_dated"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Indexed because both the reminder job and the at-risk board filter on it.
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[MilestoneStatus] = mapped_column(
        Enum(
            MilestoneStatus,
            name="milestone_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        server_default=MilestoneStatus.PENDING.value,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class MilestoneDependency(Base):
    """`milestone_id` waits on `depends_on_id`.

    Acyclicity is enforced in the service with a recursive walk, because no
    constraint can express it. Self-dependency is the one case a CHECK *can*
    catch, so it is caught here rather than trusted to that walk.
    """

    __tablename__ = "milestone_dependencies"
    __table_args__ = (CheckConstraint("milestone_id <> depends_on_id", name="no_self_dependency"),)

    milestone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("milestones.id", ondelete="CASCADE"), primary_key=True
    )
    depends_on_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("milestones.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["SETTLED_STATUSES", "Milestone", "MilestoneDependency", "MilestoneStatus"]
