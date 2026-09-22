"""Sending and answering collaboration requests.

Only the two parties know a request exists: anyone else gets 404. The
recipient answers, the sender cancels. Services never import FastAPI.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.collaborations.models import CollaborationRequest, CollaborationStatus
from app.modules.collaborations.policies import Actor, assert_transition, can_contact
from app.modules.collaborations.schemas import Box, CollaborationCreate, CollaborationRead, Party
from app.modules.profiles.models import StudentProfile
from app.modules.projects.models import Project
from app.modules.projects.policies import visibility_filter as project_visibility
from app.modules.users.models import User


class CollaborationNotFoundError(Exception):
    """No such request, or the caller isn't a party to it."""


class RecipientNotFoundError(Exception):
    """No contactable user with that id (missing, inactive, private student, admin)."""


class SelfRequestError(Exception):
    """You can't send a request to yourself."""


class ProjectNotFoundError(Exception):
    """The project doesn't exist or isn't visible to the sender."""


class DuplicatePendingError(Exception):
    """A pending request to this person about this project already exists."""


def _load(db: Session, viewer: User, request_id: uuid.UUID) -> CollaborationRequest:
    request = db.get(CollaborationRequest, request_id)
    if request is None or viewer.id not in (request.sender_id, request.recipient_id):
        raise CollaborationNotFoundError
    return request


def _to_reads(
    db: Session, viewer: User, rows: Sequence[CollaborationRequest]
) -> list[CollaborationRead]:
    if not rows:
        return []
    user_ids = {r.sender_id for r in rows} | {r.recipient_id for r in rows}
    parties = {
        u.id: Party(id=u.id, full_name=u.full_name, role=u.role)
        for u in db.execute(select(User).where(User.id.in_(user_ids))).scalars()
    }
    project_ids = {r.project_id for r in rows if r.project_id is not None}
    titles: dict[uuid.UUID, str] = {}
    if project_ids:
        titles = {
            pid: title
            for pid, title in db.execute(
                select(Project.id, Project.title).where(
                    Project.id.in_(project_ids),
                    Project.deleted_at.is_(None),
                    project_visibility(viewer),
                )
            ).all()
        }
    return [
        CollaborationRead(
            id=r.id,
            sender=parties[r.sender_id],
            recipient=parties[r.recipient_id],
            project_id=r.project_id,
            project_title=titles.get(r.project_id) if r.project_id else None,
            message=r.message,
            status=r.status,
            responded_at=r.responded_at,
            created_at=r.created_at,
        )
        for r in rows
    ]


def send_request(db: Session, sender: User, data: CollaborationCreate) -> CollaborationRead:
    if data.recipient_id == sender.id:
        raise SelfRequestError
    row = db.execute(
        select(User, StudentProfile.is_discoverable)
        .outerjoin(StudentProfile, StudentProfile.user_id == User.id)
        .where(User.id == data.recipient_id, User.is_active.is_(True))
    ).one_or_none()
    if row is None or not can_contact(row[0].role, bool(row[1])):
        raise RecipientNotFoundError

    if data.project_id is not None:
        visible = db.execute(
            select(Project.id).where(
                Project.id == data.project_id,
                Project.deleted_at.is_(None),
                project_visibility(sender),
            )
        ).scalar_one_or_none()
        if visible is None:
            raise ProjectNotFoundError

    request = CollaborationRequest(
        sender_id=sender.id,
        recipient_id=data.recipient_id,
        project_id=data.project_id,
        message=data.message,
    )
    db.add(request)
    try:
        # The partial unique index is the duplicate guard, so two concurrent
        # sends can't both create a pending request.
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicatePendingError from exc
    db.refresh(request)
    return _to_reads(db, sender, [request])[0]


def get_request(db: Session, viewer: User, request_id: uuid.UUID) -> CollaborationRead:
    return _to_reads(db, viewer, [_load(db, viewer, request_id)])[0]


def list_requests(
    db: Session, viewer: User, box: Box, status: CollaborationStatus | None = None
) -> list[CollaborationRead]:
    column = (
        CollaborationRequest.recipient_id if box is Box.INBOX else CollaborationRequest.sender_id
    )
    query = select(CollaborationRequest).where(column == viewer.id)
    if status is not None:
        query = query.where(CollaborationRequest.status == status)
    rows = db.execute(query.order_by(CollaborationRequest.created_at.desc())).scalars().all()
    return _to_reads(db, viewer, rows)


def respond(
    db: Session, actor: User, request_id: uuid.UUID, target: CollaborationStatus
) -> CollaborationRead:
    request = _load(db, actor, request_id)
    party: Actor = "sender" if request.sender_id == actor.id else "recipient"
    assert_transition(request.status, target, party)
    request.status = target
    request.responded_at = datetime.now(UTC)
    db.commit()
    db.refresh(request)
    return _to_reads(db, actor, [request])[0]
