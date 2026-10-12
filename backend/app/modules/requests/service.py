"""Personal requests: submit one, move it along, and read what you are party to.

Every read path goes through `policies.visibility_filter`, including the
attachment download, so there is no route to a request or its files that
skips the check. A request belongs to exactly two people; a third gets 404,
administrators included, the same answer a conversation thread gives.

The two refusals are ordered the way the patent pipeline orders them. A move
that does NOT EXIST is 409 whoever asks; a move that exists but is the other
party's is 403. Checked that way round, or a sender asking to resolve their
own request is told it is merely somebody else's to make -- when the honest
answer is that resolving is not a thing a sender ever does.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams
from app.core.permissions import REQUEST_RECIPIENT_ROLES
from app.modules.admin.models import Department
from app.modules.notifications.models import NotificationType
from app.modules.notifications.service import notify
from app.modules.requests import policies
from app.modules.requests.models import (
    DECIDED_STATUSES,
    PersonalRequest,
    RequestAttachment,
    RequestStatus,
)
from app.modules.requests.schemas import (
    RequestAttachmentRead,
    RequestCreate,
    RequestRead,
    RequestRecipient,
)
from app.modules.uploads import validation
from app.modules.users.models import User


class RequestNotFoundError(Exception):
    """No such request, or none this viewer is party to. The same answer to both."""


class UnknownRecipientError(Exception):
    """Nobody by that id this sender may address."""


class NotYourMoveError(Exception):
    """The move exists, but it belongs to the other party."""


class ImpossibleMoveError(Exception):
    """Nobody can make this move from where the request is."""


class ReasonRequiredError(Exception):
    """Declining without one. Refused in three places, and this is the second."""


def _attachments_for(
    db: Session, request_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[RequestAttachmentRead]]:
    """Filenames and sizes, never the bytes.

    Selecting `data` to print a name would drag every attached file through
    the response layer to render a list.
    """
    result: dict[uuid.UUID, list[RequestAttachmentRead]] = {}
    if not request_ids:
        return result
    for attachment_id, request_id, filename, content_type, byte_size in db.execute(
        select(
            RequestAttachment.id,
            RequestAttachment.request_id,
            RequestAttachment.filename,
            RequestAttachment.content_type,
            RequestAttachment.byte_size,
        )
        .where(RequestAttachment.request_id.in_(request_ids))
        .order_by(RequestAttachment.created_at)
    ).all():
        result.setdefault(request_id, []).append(
            RequestAttachmentRead(
                id=attachment_id,
                filename=filename,
                content_type=content_type,
                byte_size=byte_size,
            )
        )
    return result


def _senders_for(db: Session, rows: Sequence[PersonalRequest]) -> dict[uuid.UUID, User]:
    """The sender rows, looked up once per page rather than once per request."""
    ids = {row.sender_id for row in rows}
    if not ids:
        return {}
    return {user.id: user for user in db.execute(select(User).where(User.id.in_(ids))).scalars()}


def _read_model(
    row: PersonalRequest,
    viewer: User,
    *,
    sender: User | None,
    attachments: list[RequestAttachmentRead],
) -> RequestRead:
    return RequestRead(
        id=row.id,
        subject=row.subject,
        body=row.body,
        category=row.category,
        status=row.status,
        sender_id=row.sender_id,
        # The sender always exists -- the FK cascades -- but a page built
        # from a stale list should still render rather than raise.
        sender_name=sender.full_name if sender else "",
        sender_registration_number=sender.registration_number if sender else "",
        sender_role=row.sender_role,
        recipient_id=row.recipient_id,
        recipient_name=row.recipient_name,
        recipient_role=row.recipient_role,
        resolution_note=row.resolution_note,
        decided_at=row.decided_at,
        attachments=attachments,
        next_statuses=policies.next_statuses(row, viewer),
        viewer_is_sender=row.sender_id == viewer.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _reads(db: Session, rows: Sequence[PersonalRequest], viewer: User) -> list[RequestRead]:
    attachments = _attachments_for(db, [row.id for row in rows])
    senders = _senders_for(db, rows)
    return [
        _read_model(
            row,
            viewer,
            sender=senders.get(row.sender_id),
            attachments=attachments.get(row.id, []),
        )
        for row in rows
    ]


def _load_visible(db: Session, request_id: uuid.UUID, viewer: User) -> PersonalRequest:
    """One request, or 404. The single place a request is fetched for a reader."""
    row = db.execute(
        select(PersonalRequest).where(
            PersonalRequest.id == request_id, policies.visibility_filter(viewer)
        )
    ).scalar_one_or_none()
    if row is None:
        raise RequestNotFoundError
    return row


def addressable(db: Session, sender: User) -> list[RequestRecipient]:
    """Who this person may put a request to.

    Built from `policies.addressable_filter`, the same filter the submit
    check runs, so the picker can never offer somebody the submit would
    refuse -- the rule the facility custodian candidate list already holds.
    """
    rows = db.execute(
        select(User, Department.name)
        .outerjoin(Department, Department.id == User.department_id)
        .where(policies.addressable_filter(sender))
        # Seniority first, then by name: a student looking for their
        # supervisor should not have to read past the whole department.
        .order_by(User.role, User.full_name)
    ).all()
    return [
        RequestRecipient(
            id=user.id,
            full_name=user.full_name,
            registration_number=user.registration_number,
            role=user.role,
            department_id=user.department_id,
            department_name=department_name,
        )
        for user, department_name in rows
    ]


def _page(
    db: Session, stmt: Select[tuple[PersonalRequest]], params: PageParams, viewer: User
) -> Page[RequestRead]:
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = list(
        db.execute(
            stmt.order_by(PersonalRequest.created_at.desc(), PersonalRequest.id.desc())
            .offset(params.offset)
            .limit(params.page_size)
        )
        .scalars()
        .all()
    )
    return Page(
        items=_reads(db, rows, viewer),
        page=params.page,
        page_size=params.page_size,
        total=total,
    )


def list_sent(
    db: Session, params: PageParams, viewer: User, *, status: RequestStatus | None = None
) -> Page[RequestRead]:
    stmt = select(PersonalRequest).where(PersonalRequest.sender_id == viewer.id)
    if status is not None:
        stmt = stmt.where(PersonalRequest.status == status)
    return _page(db, stmt, params, viewer)


def list_inbox(
    db: Session, params: PageParams, viewer: User, *, status: RequestStatus | None = None
) -> Page[RequestRead]:
    stmt = select(PersonalRequest).where(PersonalRequest.recipient_id == viewer.id)
    if status is not None:
        stmt = stmt.where(PersonalRequest.status == status)
    return _page(db, stmt, params, viewer)


def waiting_count(db: Session, viewer: User) -> int:
    """What this person still owes an answer on.

    Submitted and under review both count: taking something up is not
    answering it, and a badge that cleared on the first click would let a
    request sit forever.
    """
    return db.execute(
        select(func.count())
        .select_from(PersonalRequest)
        .where(
            PersonalRequest.recipient_id == viewer.id,
            PersonalRequest.status.in_([RequestStatus.SUBMITTED, RequestStatus.UNDER_REVIEW]),
        )
    ).scalar_one()


def get_request(db: Session, request_id: uuid.UUID, viewer: User) -> RequestRead:
    row = _load_visible(db, request_id, viewer)
    return _reads(db, [row], viewer)[0]


def submit(db: Session, sender: User, data: RequestCreate) -> RequestRead:
    """Put a request to somebody above you.

    `may_address` re-checks the named recipient against the same filter that
    built the candidate list. It is not a second opinion from the role alone:
    the department check has to run against the stored row, or a sender could
    name a coordinator from another school whose role happens to be permitted.
    """
    if not REQUEST_RECIPIENT_ROLES[sender.role]:
        # An administrator addresses nobody, so there is no recipient to look
        # up and the answer is about the sender, not about the person named.
        raise UnknownRecipientError
    recipient = db.execute(
        select(User).where(User.id == data.recipient_id, policies.addressable_filter(sender))
    ).scalar_one_or_none()
    if recipient is None:
        raise UnknownRecipientError

    row = PersonalRequest(
        subject=data.subject,
        body=data.body,
        category=data.category,
        sender_id=sender.id,
        # Frozen: the routing rule was evaluated against THIS role, and a
        # later promotion must not make a historical request look like one
        # the rules would have refused.
        sender_role=sender.role,
        recipient_id=recipient.id,
        recipient_role=recipient.role,
        recipient_name=recipient.full_name,
        status=RequestStatus.SUBMITTED,
    )
    db.add(row)
    db.flush()
    notify(
        db,
        user_id=recipient.id,
        notification_type=NotificationType.REQUEST_RECEIVED,
        payload={
            "request_id": str(row.id),
            "subject": row.subject,
            "category": row.category.value,
            "from_name": sender.full_name,
            "from_registration_number": sender.registration_number,
            "from_role": sender.role.value,
        },
    )
    db.commit()
    db.refresh(row)
    return _reads(db, [row], sender)[0]


def change_status(
    db: Session,
    request_id: uuid.UUID,
    actor: User,
    target: RequestStatus,
    note: str | None,
) -> RequestRead:
    """Move a request along, or retract it.

    One table answers for both actors (`policies.TRANSITIONS`), the way
    milestones serve members and owners from one table.
    """
    row = _load_visible(db, request_id, actor)
    side = policies.side_of(row, actor)
    if side is None:  # pragma: no cover - _load_visible already refused
        raise RequestNotFoundError

    allowed = policies.actors_for(row.status, target)
    if not allowed:
        # Nobody can make this move from here -- 409 whoever asks, BEFORE the
        # ownership check, or a sender is told that resolving their own
        # request is merely somebody else's to do.
        raise ImpossibleMoveError
    if side not in allowed:
        raise NotYourMoveError

    cleaned = (note or "").strip() or None
    if target is RequestStatus.DECLINED and cleaned is None:
        # The schema refuses it, this refuses it, and a CHECK refuses it.
        # "No" without a reason is what stops the next person asking.
        raise ReasonRequiredError

    row.status = target
    if target in DECIDED_STATUSES:
        row.decided_at = datetime.now(UTC)
        row.decided_by = actor.id
        row.resolution_note = cleaned
    elif cleaned is not None:
        # A note on a non-decision -- "I am looking at this" -- is kept, but
        # it never counts as the decision's reason.
        row.resolution_note = cleaned

    if target in DECIDED_STATUSES:
        notify(
            db,
            user_id=row.sender_id,
            notification_type=NotificationType.REQUEST_DECIDED,
            payload={
                "request_id": str(row.id),
                "subject": row.subject,
                "status": target.value,
                "note": cleaned or "",
                "by_name": actor.full_name,
            },
        )
    db.commit()
    db.refresh(row)
    return _reads(db, [row], actor)[0]


def add_attachment(
    db: Session,
    request_id: uuid.UUID,
    actor: User,
    *,
    data: bytes,
    filename: str | None,
    max_bytes: int,
) -> RequestRead:
    """Attach a supporting document.

    The SENDER's, and only while the request is still open to an answer.
    Letting either side add to a decided request would change what the other
    one answered, after they answered it.

    The type comes from the BYTES (`uploads.validation`), never the filename
    or the browser's Content-Type.
    """
    row = _load_visible(db, request_id, actor)
    if row.status in policies.TERMINAL_STATUSES:
        raise ImpossibleMoveError
    if row.sender_id != actor.id:
        raise NotYourMoveError

    kind = validation.validate(data, max_bytes=max_bytes)
    db.add(
        RequestAttachment(
            request_id=row.id,
            filename=validation.safe_filename(filename, kind),
            content_type=kind.content_type,
            byte_size=len(data),
            data=data,
        )
    )
    db.commit()
    db.refresh(row)
    return _reads(db, [row], actor)[0]


def remove_attachment(
    db: Session, request_id: uuid.UUID, attachment_id: uuid.UUID, actor: User
) -> None:
    row = _load_visible(db, request_id, actor)
    if row.status in policies.TERMINAL_STATUSES:
        raise ImpossibleMoveError
    if row.sender_id != actor.id:
        raise NotYourMoveError
    attachment = db.execute(
        select(RequestAttachment).where(
            RequestAttachment.id == attachment_id,
            # Scoped to the request in the path, so an id belonging to
            # another request cannot be removed through this one.
            RequestAttachment.request_id == row.id,
        )
    ).scalar_one_or_none()
    if attachment is None:
        raise RequestNotFoundError
    db.delete(attachment)
    db.commit()


def read_attachment(
    db: Session, request_id: uuid.UUID, attachment_id: uuid.UUID, viewer: User
) -> RequestAttachment:
    """The bytes, for the two people party to the request and nobody else.

    Runs the request's own visibility check and scopes the attachment id to
    the request in the path. There is no public path to these bytes, which is
    why the frontend fetches them through the API client: an `<a href>` sends
    no Authorization header.
    """
    _load_visible(db, request_id, viewer)
    attachment = db.execute(
        select(RequestAttachment).where(
            RequestAttachment.id == attachment_id,
            RequestAttachment.request_id == request_id,
        )
    ).scalar_one_or_none()
    if attachment is None:
        raise RequestNotFoundError
    return attachment
