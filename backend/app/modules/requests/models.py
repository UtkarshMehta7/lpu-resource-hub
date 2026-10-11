"""A personal request: one person asking a named person above them to act.

This is the only place on the platform where a sender NAMES their recipient,
and that is a deliberate reversal of the nudge rule. `POST /nudges` takes a
kind and an entity and resolves who hears about it from the thing being
chased (ADR 0031), precisely so it cannot become a way to message anyone in
the institution. A request needs the opposite: "my supervisor has not signed
my form" is addressed to a person, and nobody else can act on it.

What stops it being the general messaging route nudges refused to be is
`REQUEST_RECIPIENT_ROLES` plus a department check -- upward only, and within
your own department unless the recipient answers to the institution. See
ADR 0039.
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
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.users.models import UserRole


class RequestCategory(StrEnum):
    """What the request is about, so an inbox can be read in priority order.

    Deliberately coarse. A long list would be a taxonomy nobody maintains,
    and the subject line carries the detail.
    """

    ACADEMIC = "academic"
    FACILITY = "facility"
    FUNDING = "funding"
    ADMINISTRATIVE = "administrative"
    OTHER = "other"


class RequestStatus(StrEnum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    DECLINED = "declined"
    #: The sender's own retraction. Distinct from DECLINED, because "I no
    #: longer need this" and "the answer is no" are different outcomes and a
    #: queue read as the second would be misleading.
    WITHDRAWN = "withdrawn"


#: The statuses that claim a decision was taken, and so must carry its date.
DECIDED_STATUSES = frozenset({RequestStatus.RESOLVED, RequestStatus.DECLINED})


class PersonalRequest(Base):
    __tablename__ = "personal_requests"
    __table_args__ = (
        # Nobody asks themselves. The service refuses it too, but a row like
        # this would make the upward-only rule meaningless, so the database
        # says so as well.
        CheckConstraint("sender_id <> recipient_id", name="request_is_not_to_oneself"),
        # "Done is never undated" -- the milestones' rule and the patent
        # pipeline's, applied to a decision.
        CheckConstraint(
            "status NOT IN ('resolved', 'declined') OR decided_at IS NOT NULL",
            name="decided_request_is_dated",
        ),
        # Declining REQUIRES a reason, in the service and here. "No" without
        # one is what stops the next person asking -- the same rule the
        # patent pipeline holds for declining a disclosure.
        CheckConstraint(
            "status <> 'declined' OR resolution_note IS NOT NULL",
            name="declined_request_carries_a_reason",
        ),
        Index("ix_personal_requests_recipient_status", "recipient_id", "status"),
        Index("ix_personal_requests_sender_status", "sender_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[RequestCategory] = mapped_column(
        Enum(
            RequestCategory,
            name="request_category",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    #: CASCADE: the request is the sender's, and goes with their account.
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Frozen at submit time: the routing rule was evaluated against THIS
    #: role, and a later promotion must not make a historical request look
    #: like one the rules would have refused.
    sender_role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda enum: [member.value for member in enum],
            create_type=False,
        ),
        nullable=False,
    )
    #: SET NULL, not CASCADE: if the recipient's account goes, the sender's
    #: request and its history must not vanish with it. The frozen name and
    #: role below are what keep the row readable afterwards.
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recipient_role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda enum: [member.value for member in enum],
            create_type=False,
        ),
        nullable=False,
    )
    recipient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(
            RequestStatus,
            name="request_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        server_default=RequestStatus.SUBMITTED.value,
        index=True,
    )
    #: The recipient's answer. Required when declining, optional when
    #: resolving -- "done" needs no justification, "no" does.
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class RequestAttachment(Base):
    """A supporting document on a request, bytes and all.

    The same shape as `message_attachments` and `announcement_attachments`,
    for the same reason: bytes on this row, so the FK cascade reaps them and
    no blob outlives the thing that referenced it.

    Reachable by the sender and the recipient only -- the download runs the
    request's own visibility check, so there is no path to these bytes that
    skips it. `content_type` is the SNIFFED type, never what the client
    declared (app/modules/uploads/validation.py).
    """

    __tablename__ = "request_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("personal_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Display label only. Sanitised on the way in, never used as a path.
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
