"""Announcements: a notice from the institution to the people in it.

Every other notification on this platform is personal and *caused* -- something
happened to you, or involving you. Nothing could say one thing to everybody,
so the IP cell had no way to tell the institution that a disclosure window
closes on Friday. This is that channel, and it is deliberately the only one.

A notice is read from a board, not delivered. `AnnouncementRead` carries one
row per person who has opened one, which is what gives an unread count without
writing a notification row per account on every post: one notice stays one
row, whether the institution has fifty people in it or fifty thousand.
"""

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
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.users.models import UserRole


class AnnouncementAudience(StrEnum):
    """Who a notice is addressed to.

    Not who may *read* it -- every role reads what is addressed to them, with
    no permission required. This is the reach of the person posting:
    institution-wide is an administrator's or the dean's to use, and a
    coordinator's voice carries across their own department, which is the
    scope their role has everywhere else in this schema.
    """

    INSTITUTION = "institution"
    DEPARTMENT = "department"


class AnnouncementStatus(StrEnum):
    #: Written, and visible to its author alone. Attachments are uploaded
    #: against the saved row, so there has to be a stage before anyone else
    #: can see it -- or a notice appears on the board without its documents.
    DRAFT = "draft"
    PUBLISHED = "published"
    #: Taken down. Said to everybody is not unsayable, but it can at least
    #: stop being said.
    WITHDRAWN = "withdrawn"


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (
        CheckConstraint(
            "audience <> 'department' OR department_id IS NOT NULL",
            name="department_notice_names_its_department",
        ),
        # A status claiming an event carries that event's date -- the same
        # rule the milestones and the patent pipeline are held to.
        CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL",
            name="published_notice_is_dated",
        ),
        Index("ix_announcements_search_document", "search_document", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    audience: Mapped[AnnouncementAudience] = mapped_column(
        Enum(
            AnnouncementAudience,
            name="announcement_audience",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    #: Set when and only when `audience` is DEPARTMENT, per the CHECK above.
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    #: SET NULL, not CASCADE: a notice outlives the account that posted it.
    #: Deleting a coordinator must not silently retract what they announced.
    posted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    #: Frozen at post time, and the reason `posted_by` may go null without the
    #: notice losing its meaning: "from the Dean of Research" is part of what
    #: was said, and it must not change if that person is later made an admin.
    posted_by_role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda enum: [member.value for member in enum],
            create_type=False,
        ),
        nullable=False,
    )
    #: Likewise frozen: the board says who spoke, not who they are now.
    posted_by_name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Set when the notice was raised FROM an opening rather than written
    #: (ADR 0041). UNIQUE, so publishing an opening twice cannot put it on the
    #: board twice -- a duplicate is impossible in the database rather than
    #: guarded in a service somebody can forget, the rule `collaborations`
    #: holds. CASCADE because a notice about an opening that no longer exists
    #: is not a notice about anything.
    source_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    status: Mapped[AnnouncementStatus] = mapped_column(
        Enum(
            AnnouncementStatus,
            name="announcement_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        server_default=AnnouncementStatus.DRAFT.value,
        index=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    #: Searched within the board itself (`?q=`). Deliberately NOT registered
    #: with the global search module: a notice is not a research entity, and
    #: adding an EntityType would put it in the embedding pipeline and the
    #: cross-entity results, which is not what a notice board is for.
    search_document: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(subject, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(body, '')), 'B')",
            persisted=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AnnouncementLink(Base):
    """A link on a notice, as its own row rather than a URL pasted in the body.

    So that a reader gets a labelled link they can click and the board can show
    how many there are, rather than prose with "http" in it somewhere.
    """

    __tablename__ = "announcement_links"
    __table_args__ = (
        UniqueConstraint("announcement_id", "position", name="uq_announcement_link_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    announcement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("announcements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    #: The author's order, which is the order it is read in.
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class AnnouncementAttachment(Base):
    """A file on a notice, bytes and all.

    The same shape as `message_attachments` and for the same reason: bytes on
    this row, so the FK cascade is what reaps them and there is never a blob
    outliving the thing that referenced it.

    `content_type` is the SNIFFED type, never what the client declared -- see
    app/modules/uploads/validation.py. The download route re-runs the notice's
    own visibility check, so there is no path to these bytes that skips it.
    """

    __tablename__ = "announcement_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    announcement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("announcements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Display label only. Sanitised on the way in, and never used as a path.
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AnnouncementReceipt(Base):
    """One row per person who has opened a notice.

    This is the whole delivery mechanism. The alternative -- a notification per
    recipient per notice -- makes one post cost a row per account, which is the
    fan-out this design exists to avoid. The unread count is a NOT EXISTS
    against this table, so an institution of any size posts one row.
    """

    __tablename__ = "announcement_reads"

    announcement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("announcements.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
