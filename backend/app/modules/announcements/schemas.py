"""Announcement schemas.

`audience`, `department_id`, `posted_by*`, `status` and `published_at` are all
absent from the write schemas on purpose. The audience is derived from the
poster (see policies.reach_of) and the rest are the service's to set -- an
`audience` field is exactly how a coordinator would acquire an
institution-wide voice.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.modules.announcements.models import AnnouncementAudience, AnnouncementStatus
from app.modules.users.models import UserRole

SUBJECT_MAX = 200
BODY_MAX = 20000
MAX_LINKS = 10


class AnnouncementLinkInput(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    url: str = Field(min_length=1, max_length=2000)

    @field_validator("url")
    @classmethod
    def _http_only(cls, value: str) -> str:
        """http(s) only.

        A notice is read by the whole institution, so a `javascript:` or
        `data:` URL on it would be a stored script with an audience. Refused
        here as well as escaped on render, because one of those alone is a
        single point of failure.
        """
        if not value.startswith(("http://", "https://")):
            raise ValueError("A link must start with http:// or https://")
        return value


class AnnouncementCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=SUBJECT_MAX)
    body: str = Field(min_length=1, max_length=BODY_MAX)
    links: list[AnnouncementLinkInput] = Field(default_factory=list, max_length=MAX_LINKS)


class AnnouncementUpdate(BaseModel):
    subject: str | None = Field(default=None, min_length=1, max_length=SUBJECT_MAX)
    body: str | None = Field(default=None, min_length=1, max_length=BODY_MAX)
    #: Replaces the whole list when present; absent leaves the links alone.
    links: list[AnnouncementLinkInput] | None = Field(default=None, max_length=MAX_LINKS)


class AnnouncementLinkRead(BaseModel):
    id: uuid.UUID
    label: str | None
    url: str


class AnnouncementAttachmentRead(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    byte_size: int


class AnnouncementRead(BaseModel):
    id: uuid.UUID
    subject: str
    body: str
    audience: AnnouncementAudience
    department_id: uuid.UUID | None
    #: The department's NAME, so the board never shows a reader a UUID.
    department_name: str | None
    posted_by: uuid.UUID | None
    posted_by_name: str
    posted_by_role: UserRole
    status: AnnouncementStatus
    published_at: datetime | None
    links: list[AnnouncementLinkRead]
    attachments: list[AnnouncementAttachmentRead]
    #: False for the author's own drafts, which nobody else can have read.
    unread: bool
    created_at: datetime
    updated_at: datetime


class UnreadCount(BaseModel):
    unread: int
