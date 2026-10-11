"""Personal request schemas.

`status`, `sender_*`, `recipient_role`, `recipient_name`, `decided_*` are all
absent from the write schemas: the sender names only *who* and *what*, and
everything about where the request sits is the service's to set.

`recipient_id` IS client-supplied, which is the whole departure from the nudge
design -- and why `policies.may_address` re-checks it against the same filter
that built the candidate list, rather than trusting that the interface only
offered valid people.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.modules.requests.models import RequestCategory, RequestStatus
from app.modules.users.models import UserRole

SUBJECT_MAX = 200
BODY_MAX = 10000
NOTE_MAX = 5000


class RequestCreate(BaseModel):
    recipient_id: uuid.UUID
    subject: str = Field(min_length=1, max_length=SUBJECT_MAX)
    body: str = Field(min_length=1, max_length=BODY_MAX)
    category: RequestCategory


class RequestStatusChange(BaseModel):
    status: RequestStatus
    note: str | None = Field(default=None, max_length=NOTE_MAX)

    @model_validator(mode="after")
    def _declining_needs_a_reason(self) -> Self:
        """Refused here as well as in the service and as a CHECK.

        Three places, because "no" without a reason is what stops the next
        person asking, and the message a sender sees should say so before the
        request is ever written.
        """
        if self.status is RequestStatus.DECLINED and not (self.note or "").strip():
            raise ValueError("Declining a request requires a reason.")
        return self


class RequestAttachmentRead(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    byte_size: int


class RequestRecipient(BaseModel):
    """Somebody the caller may address.

    Carries the department NAME and the registration number, because a
    picker offering three people called "Gurpreet" is not a picker. The UID
    is shown wherever a person is named, per ADR 0020.
    """

    id: uuid.UUID
    full_name: str
    registration_number: str
    role: UserRole
    department_id: uuid.UUID | None
    department_name: str | None


class RequestRead(BaseModel):
    id: uuid.UUID
    subject: str
    body: str
    category: RequestCategory
    status: RequestStatus

    sender_id: uuid.UUID
    sender_name: str
    sender_registration_number: str
    sender_role: UserRole

    #: None once the recipient's account is gone; the name and role below
    #: still read, which is why they are frozen on the row.
    recipient_id: uuid.UUID | None
    recipient_name: str
    recipient_role: UserRole

    resolution_note: str | None
    decided_at: datetime | None

    attachments: list[RequestAttachmentRead]
    #: Computed per reader, so the interface cannot offer a move the service
    #: would refuse.
    next_statuses: list[RequestStatus]
    #: Which side of it this reader is on.
    viewer_is_sender: bool

    created_at: datetime
    updated_at: datetime


class InboxCount(BaseModel):
    """What the recipient still owes an answer on."""

    waiting: int
