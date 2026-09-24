"""Conversation threads, scoped to a relationship that already exists.

A thread is never a fresh channel between two arbitrary people: it belongs to
an *accepted* collaboration request or to a project team. That is what makes
it safe -- somebody already agreed, so there is no new way to reach a student
who never opted in to being reachable (ADR 0022).

`conversations` therefore carries two nullable foreign keys rather than one
polymorphic `subject_id`, with a CHECK that exactly one is set. The same shape
as `tag_aliases`, and for the same reason: they are real foreign keys, so a
deleted project or request takes its thread with it. A polymorphic id cannot
cascade, and would leave threads pointing at nothing forever.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

#: Long enough for a real paragraph, short enough that one message cannot be
#: used to dump a document into somebody's inbox.
MESSAGE_MAX_LENGTH = 4000


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "(collaboration_request_id IS NULL) <> (project_id IS NULL)",
            name="exactly_one_subject",
        ),
        # One thread per subject. Accepting a request twice, or two members
        # opening a project thread at once, cannot produce a second one.
        UniqueConstraint("collaboration_request_id", name="uq_conversations_collaboration"),
        UniqueConstraint("project_id", name="uq_conversations_project"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    collaboration_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collaboration_requests.id", ondelete="CASCADE"),
        nullable=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    #: Denormalised so the conversation list can be ordered without joining
    #: every thread's messages. Updated whenever a message is sent.
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ConversationParticipant(Base):
    """Who may read and write in a thread, and how far they have read.

    Membership lives here rather than being derived on every request so that
    leaving a project revokes access without rewriting the messages: the row
    goes, the messages stay attributed.
    """

    __tablename__ = "conversation_participants"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    #: NULL means they have never opened it, so everything is unread.
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    muted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # The keyset the poll cursor walks: newest-after-(created_at, id).
        Index("ix_messages_thread_order", "conversation_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # No index=True: ix_messages_thread_order below already leads with this
    # column, so a second index on it alone would only cost write time.
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    #: Moderation hides a message; it never deletes the row, so a thread does
    #: not develop holes and the other party can still follow the exchange.
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hidden_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
