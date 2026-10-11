"""Announcements: post, read, and count what has not been read.

Every read path goes through `policies.visibility_filter`, including the
attachment download, so there is no route to a notice or its files that skips
the check. A notice the viewer may not see is a 404 and never a 403 -- the
board must not tell a student that a department they are not in has notices.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams
from app.modules.admin.models import Department
from app.modules.announcements import policies
from app.modules.announcements.models import (
    Announcement,
    AnnouncementAttachment,
    AnnouncementLink,
    AnnouncementReceipt,
    AnnouncementStatus,
)
from app.modules.announcements.schemas import (
    AnnouncementAttachmentRead,
    AnnouncementCreate,
    AnnouncementLinkInput,
    AnnouncementLinkRead,
    AnnouncementRead,
    AnnouncementUpdate,
)
from app.modules.uploads import validation
from app.modules.users.models import User


class AnnouncementNotFoundError(Exception):
    """No such notice, or none this viewer may see. The same answer to both."""


class NotYoursError(Exception):
    """The notice exists and is visible, but this is somebody else's to change."""


class WrongStatusError(Exception):
    """The notice is not in a state where this makes sense."""


@dataclass(frozen=True, slots=True)
class _Extras:
    links: dict[uuid.UUID, list[AnnouncementLinkRead]]
    attachments: dict[uuid.UUID, list[AnnouncementAttachmentRead]]
    departments: dict[uuid.UUID, str]
    unread: set[uuid.UUID]


def _load_extras(db: Session, rows: Sequence[Announcement], viewer: User) -> _Extras:
    """Everything the read model needs beside the row itself, in four queries.

    Looked up once per page rather than per notice -- the N+1 the researcher
    cards had before `department_name` was batched.
    """
    ids = [row.id for row in rows]
    if not ids:
        return _Extras({}, {}, {}, set())

    links: dict[uuid.UUID, list[AnnouncementLinkRead]] = {}
    for link in db.execute(
        select(AnnouncementLink)
        .where(AnnouncementLink.announcement_id.in_(ids))
        .order_by(AnnouncementLink.position)
    ).scalars():
        links.setdefault(link.announcement_id, []).append(
            AnnouncementLinkRead(id=link.id, label=link.label, url=link.url)
        )

    attachments: dict[uuid.UUID, list[AnnouncementAttachmentRead]] = {}
    # Never select `data` here: a page of notices would otherwise drag every
    # attached file's bytes through the response layer to print its name.
    for attachment_id, announcement_id, filename, content_type, byte_size in db.execute(
        select(
            AnnouncementAttachment.id,
            AnnouncementAttachment.announcement_id,
            AnnouncementAttachment.filename,
            AnnouncementAttachment.content_type,
            AnnouncementAttachment.byte_size,
        )
        .where(AnnouncementAttachment.announcement_id.in_(ids))
        .order_by(AnnouncementAttachment.created_at)
    ).all():
        attachments.setdefault(announcement_id, []).append(
            AnnouncementAttachmentRead(
                id=attachment_id,
                filename=filename,
                content_type=content_type,
                byte_size=byte_size,
            )
        )

    department_ids = {row.department_id for row in rows if row.department_id is not None}
    departments: dict[uuid.UUID, str] = {}
    if department_ids:
        departments = {
            department_id: name
            for department_id, name in db.execute(
                select(Department.id, Department.name).where(Department.id.in_(department_ids))
            ).all()
        }

    read_ids = set(
        db.execute(
            select(AnnouncementReceipt.announcement_id).where(
                AnnouncementReceipt.announcement_id.in_(ids),
                AnnouncementReceipt.user_id == viewer.id,
            )
        )
        .scalars()
        .all()
    )
    unread = {
        row.id
        for row in rows
        if row.id not in read_ids and row.status is AnnouncementStatus.PUBLISHED
    }
    return _Extras(links, attachments, departments, unread)


def _read_model(row: Announcement, extras: _Extras) -> AnnouncementRead:
    return AnnouncementRead(
        id=row.id,
        subject=row.subject,
        body=row.body,
        audience=row.audience,
        department_id=row.department_id,
        department_name=(
            extras.departments.get(row.department_id) if row.department_id is not None else None
        ),
        posted_by=row.posted_by,
        posted_by_name=row.posted_by_name,
        posted_by_role=row.posted_by_role,
        status=row.status,
        published_at=row.published_at,
        links=extras.links.get(row.id, []),
        attachments=extras.attachments.get(row.id, []),
        unread=row.id in extras.unread,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def announcement_reads(
    db: Session, rows: Sequence[Announcement], viewer: User
) -> list[AnnouncementRead]:
    extras = _load_extras(db, rows, viewer)
    return [_read_model(row, extras) for row in rows]


def _load_visible(db: Session, announcement_id: uuid.UUID, viewer: User) -> Announcement:
    """One notice, or 404. The single place a notice is fetched for a reader."""
    row = db.execute(
        select(Announcement).where(
            Announcement.id == announcement_id, policies.visibility_filter(viewer)
        )
    ).scalar_one_or_none()
    if row is None:
        raise AnnouncementNotFoundError
    return row


def list_announcements(
    db: Session,
    params: PageParams,
    viewer: User,
    *,
    q: str | None = None,
    unread_only: bool = False,
    mine: bool = False,
) -> Page[AnnouncementRead]:
    conditions = [policies.visibility_filter(viewer)]
    if q:
        conditions.append(Announcement.search_document.op("@@")(func.plainto_tsquery("english", q)))
    if mine:
        conditions.append(Announcement.posted_by == viewer.id)
    if unread_only:
        conditions.append(
            ~select(AnnouncementReceipt.announcement_id)
            .where(
                AnnouncementReceipt.announcement_id == Announcement.id,
                AnnouncementReceipt.user_id == viewer.id,
            )
            .exists()
        )

    total = db.execute(
        select(func.count()).select_from(Announcement).where(*conditions)
    ).scalar_one()
    rows = list(
        db.execute(
            select(Announcement)
            .where(*conditions)
            # Published notices newest first; a draft has no published_at, so
            # it sorts by when it was written and stays at the top for its
            # author, which is where unfinished work belongs.
            .order_by(
                func.coalesce(Announcement.published_at, Announcement.created_at).desc(),
                Announcement.id.desc(),
            )
            .offset(params.offset)
            .limit(params.page_size)
        )
        .scalars()
        .all()
    )
    extras = _load_extras(db, rows, viewer)
    return Page(
        items=[_read_model(row, extras) for row in rows],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )


def recent_for_dashboard(
    db: Session, viewer: User, *, limit: int = 4
) -> tuple[list[AnnouncementRead], int]:
    """The few newest notices addressed to this person, and the unread count.

    For the dashboard, which is where everybody meets the board -- so this is
    the one surface every role sees, and the searchable history behind it is
    for looking something up later.

    Drafts are excluded even for their author: an unfinished notice of your
    own on your own dashboard is noise, and the author reaches it from the
    history page where it belongs.
    """
    rows = list(
        db.execute(
            select(Announcement)
            .where(
                Announcement.status == AnnouncementStatus.PUBLISHED,
                policies.visibility_filter(viewer),
            )
            .order_by(Announcement.published_at.desc(), Announcement.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    extras = _load_extras(db, rows, viewer)
    return [_read_model(row, extras) for row in rows], unread_count(db, viewer)


def get_announcement(db: Session, announcement_id: uuid.UUID, viewer: User) -> AnnouncementRead:
    row = _load_visible(db, announcement_id, viewer)
    return _read_model(row, _load_extras(db, [row], viewer))


def _assert_may_edit(actor: User, row: Announcement) -> None:
    """Refuse an edit, with the two answers in the order that matters.

    Status FIRST: editing a published notice is a move that exists for
    NOBODY, its author included, so it is 409 whoever asks. Authorship
    second: the notice is a draft somebody else owns, which is 403.

    Checked the other way round -- as this did until a test caught it -- an
    administrator patching somebody else's published notice is told it
    belongs to another person, implying that person could still make the
    change. They cannot. It is the patent pipeline's rule: a move that does
    not exist outranks a move that is not yours.
    """
    if policies.may_edit(actor, row):
        return
    if row.status is not AnnouncementStatus.DRAFT:
        raise WrongStatusError
    raise NotYoursError


def _write_links(
    db: Session, announcement_id: uuid.UUID, links: Sequence[AnnouncementLinkInput]
) -> None:
    db.execute(delete(AnnouncementLink).where(AnnouncementLink.announcement_id == announcement_id))
    for position, link in enumerate(links):
        db.add(
            AnnouncementLink(
                announcement_id=announcement_id,
                label=link.label,
                url=link.url,
                position=position,
            )
        )


def create_announcement(db: Session, actor: User, data: AnnouncementCreate) -> AnnouncementRead:
    """Write a notice as a draft.

    It reaches nobody until it is published, which is what gives the author a
    moment to attach the documents the notice is about.
    """
    audience, department_id = policies.reach_of(actor)
    row = Announcement(
        subject=data.subject,
        body=data.body,
        audience=audience,
        department_id=department_id,
        posted_by=actor.id,
        posted_by_role=actor.role,
        posted_by_name=actor.full_name,
        status=AnnouncementStatus.DRAFT,
    )
    db.add(row)
    db.flush()
    _write_links(db, row.id, data.links)
    db.commit()
    db.refresh(row)
    return _read_model(row, _load_extras(db, [row], actor))


def update_announcement(
    db: Session, announcement_id: uuid.UUID, actor: User, data: AnnouncementUpdate
) -> AnnouncementRead:
    row = _load_visible(db, announcement_id, actor)
    _assert_may_edit(actor, row)
    if data.subject is not None:
        row.subject = data.subject
    if data.body is not None:
        row.body = data.body
    if data.links is not None:
        _write_links(db, row.id, data.links)
    db.commit()
    db.refresh(row)
    return _read_model(row, _load_extras(db, [row], actor))


def publish_announcement(db: Session, announcement_id: uuid.UUID, actor: User) -> AnnouncementRead:
    row = _load_visible(db, announcement_id, actor)
    if not policies.may_publish(actor, row):
        # Status first, same as _assert_may_edit: publishing an already
        # published notice is a move nobody has.
        if row.status is not AnnouncementStatus.DRAFT:
            raise WrongStatusError
        raise NotYoursError
    row.status = AnnouncementStatus.PUBLISHED
    # Set here and not by a default: the CHECK requires a published notice to
    # carry its date, and this is the one moment that date is known.
    row.published_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return _read_model(row, _load_extras(db, [row], actor))


def withdraw_announcement(db: Session, announcement_id: uuid.UUID, actor: User) -> AnnouncementRead:
    row = _load_visible(db, announcement_id, actor)
    if not policies.may_withdraw(actor, row):
        if row.status is not AnnouncementStatus.PUBLISHED:
            raise WrongStatusError
        raise NotYoursError
    row.status = AnnouncementStatus.WITHDRAWN
    db.commit()
    db.refresh(row)
    return _read_model(row, _load_extras(db, [row], actor))


def delete_announcement(db: Session, announcement_id: uuid.UUID, actor: User) -> None:
    row = _load_visible(db, announcement_id, actor)
    if not policies.may_delete(actor, row):
        if row.status is AnnouncementStatus.PUBLISHED:
            raise WrongStatusError
        raise NotYoursError
    db.delete(row)
    db.commit()


def mark_read(db: Session, announcement_id: uuid.UUID, viewer: User) -> None:
    """Record that this person has seen it.

    ON CONFLICT DO NOTHING rather than a read-then-insert: two tabs opening
    the same notice together would otherwise race on the primary key.
    """
    _load_visible(db, announcement_id, viewer)
    db.execute(
        pg_insert(AnnouncementReceipt)
        .values(announcement_id=announcement_id, user_id=viewer.id)
        .on_conflict_do_nothing(index_elements=["announcement_id", "user_id"])
    )
    db.commit()


def unread_count(db: Session, viewer: User) -> int:
    """How many visible notices this person has not opened.

    A NOT EXISTS against `announcement_reads`, which is why posting does not
    write a row per account: the count is derived on read, the same choice
    milestone risk made.
    """
    return db.execute(
        select(func.count())
        .select_from(Announcement)
        .where(
            Announcement.status == AnnouncementStatus.PUBLISHED,
            policies.visibility_filter(viewer),
            ~select(AnnouncementReceipt.announcement_id)
            .where(
                AnnouncementReceipt.announcement_id == Announcement.id,
                AnnouncementReceipt.user_id == viewer.id,
            )
            .exists(),
        )
    ).scalar_one()


def add_attachment(
    db: Session,
    announcement_id: uuid.UUID,
    actor: User,
    *,
    data: bytes,
    filename: str | None,
    max_bytes: int,
) -> AnnouncementRead:
    """Attach a file to a draft.

    Drafts only: a notice the institution has already read must not grow a
    document afterwards, or what people saw and what the record says differ.

    The type comes from the BYTES (`uploads.validation`), never the filename
    or the browser's Content-Type, both of which the uploader chooses.
    Validation runs before anything is written.
    """
    row = _load_visible(db, announcement_id, actor)
    _assert_may_edit(actor, row)
    kind = validation.validate(data, max_bytes=max_bytes)
    db.add(
        AnnouncementAttachment(
            announcement_id=row.id,
            filename=validation.safe_filename(filename, kind),
            content_type=kind.content_type,
            byte_size=len(data),
            data=data,
        )
    )
    db.commit()
    db.refresh(row)
    return _read_model(row, _load_extras(db, [row], actor))


def remove_attachment(
    db: Session, announcement_id: uuid.UUID, attachment_id: uuid.UUID, actor: User
) -> None:
    row = _load_visible(db, announcement_id, actor)
    _assert_may_edit(actor, row)
    attachment = db.execute(
        select(AnnouncementAttachment).where(
            AnnouncementAttachment.id == attachment_id,
            # Scoped to the notice in the path, so an id belonging to another
            # notice cannot be removed through this one.
            AnnouncementAttachment.announcement_id == row.id,
        )
    ).scalar_one_or_none()
    if attachment is None:
        raise AnnouncementNotFoundError
    db.delete(attachment)
    db.commit()


def read_attachment(
    db: Session, announcement_id: uuid.UUID, attachment_id: uuid.UUID, viewer: User
) -> AnnouncementAttachment:
    """The bytes, for anyone the notice is addressed to.

    Runs the notice's own visibility check and scopes the attachment id to the
    notice in the path, so a withdrawn or departmental notice's files are no
    more reachable than the notice itself. There is no public path to these
    bytes -- which is why the frontend fetches them through the API client
    rather than an `<a href>`, since an anchor sends no Authorization header.
    """
    _load_visible(db, announcement_id, viewer)
    attachment = db.execute(
        select(AnnouncementAttachment).where(
            AnnouncementAttachment.id == attachment_id,
            AnnouncementAttachment.announcement_id == announcement_id,
        )
    ).scalar_one_or_none()
    if attachment is None:
        raise AnnouncementNotFoundError
    return attachment
