"""Research facilities and the equipment inside them."""

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

MAX_BOOKING_HOURS = 24 * 14


class MaintenanceStatus(StrEnum):
    AVAILABLE = "available"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


class Facility(Base):
    __tablename__ = "facilities"
    __table_args__ = (UniqueConstraint("department_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Which department runs it: this is what scopes a coordinator's control.
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    contact: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Equipment(Base):
    """One bookable item. The booking rules live here, not in the service."""

    __tablename__ = "equipment"
    __table_args__ = (
        CheckConstraint("max_hours > 0", name="max_hours_positive"),
        CheckConstraint("min_lead_hours >= 0", name="min_lead_hours_not_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("facilities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    maintenance_status: Mapped[MaintenanceStatus] = mapped_column(
        Enum(
            MaintenanceStatus,
            name="maintenance_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        server_default=MaintenanceStatus.AVAILABLE.value,
    )
    students_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    max_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default="8")
    min_lead_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
