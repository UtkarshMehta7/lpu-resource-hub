"""Request and response shapes for conversation threads.

Nothing here lets a client say who it is or which thread it belongs to:
`sender_id` comes from the token, membership is read from the database, and
`hidden_at` is set only by the moderation queue.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from app.modules.messages.models import MESSAGE_MAX_LENGTH
from app.modules.users.models import UserRole


class SubjectKind(StrEnum):
    """What a thread hangs off. Not stored -- derived from which foreign key
    is set -- but the client needs it to build the right link."""

    COLLABORATION = "collaboration"
    PROJECT = "project"


class Participant(BaseModel):
    user_id: uuid.UUID
    full_name: str
    registration_number: str
    role: UserRole


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=MESSAGE_MAX_LENGTH)

    @field_validator("body")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        """Trim first, then insist on something left.

        min_length alone counts spaces, so "   " passed validation and was
        stored as an empty message -- a blank bubble in the thread.
        """
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Write something before sending.")
        return trimmed


class MessageRead(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: uuid.UUID
    sender_name: str
    sender_registration_number: str
    #: None when a moderator has hidden it. The message still occupies its
    #: place in the thread; only the text is withheld.
    body: str | None
    hidden: bool
    created_at: datetime


class ConversationRead(BaseModel):
    id: uuid.UUID
    subject_kind: SubjectKind
    #: The project or the collaboration request this thread belongs to.
    subject_id: uuid.UUID
    #: "Soil sensors" for a project; the other person's name for a request.
    title: str
    participants: list[Participant]
    unread_count: int
    last_message_at: datetime | None
    #: First line of the newest message, for the list. None on a fresh thread,
    #: and None when the newest message is hidden.
    preview: str | None
    created_at: datetime


class MessagePage(BaseModel):
    """One slice of a thread, oldest first.

    `next_after` is the cursor to poll with: pass it back as `after` and only
    what arrived since comes back. It is opaque on purpose -- a keyset over
    (created_at, id), not an offset, so a message arriving mid-poll cannot
    shift the window and hide itself.
    """

    items: list[MessageRead]
    next_after: str | None
