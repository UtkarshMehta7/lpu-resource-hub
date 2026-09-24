"""Sending and answering collaboration requests.

Only the two parties know a request exists: anyone else gets 404. The
recipient answers, the sender cancels. Services never import FastAPI.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.events import EVENT_BUS, Event, EventName
from app.modules.collaborations.models import (
    Collaboration,
    CollaborationRequest,
    CollaborationState,
    CollaborationStatus,
    normalise_pair,
)
from app.modules.collaborations.policies import Actor, assert_transition, can_contact
from app.modules.collaborations.schemas import (
    Box,
    CollaborationCreate,
    CollaborationRead,
    CollaborationSummary,
    Party,
)
from app.modules.messages import service as messages_service
from app.modules.messages.models import Conversation
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


class AlreadyCollaboratingError(Exception):
    """A live relationship already exists with this person, so there is
    nothing to request. Covers both directions: the pair is one row."""


class DuplicatePendingError(Exception):
    """A pending request to this person about this project already exists."""


def _load(db: Session, viewer: User, request_id: uuid.UUID) -> CollaborationRequest:
    request = db.get(CollaborationRequest, request_id)
    if request is None or viewer.id not in (request.sender_id, request.recipient_id):
        raise CollaborationNotFoundError
    return request


logger = logging.getLogger(__name__)


def _to_reads(
    db: Session, viewer: User, rows: Sequence[CollaborationRequest]
) -> list[CollaborationRead]:
    if not rows:
        return []
    user_ids = {r.sender_id for r in rows} | {r.recipient_id for r in rows}
    parties = {
        u.id: Party(
            id=u.id,
            full_name=u.full_name,
            registration_number=u.registration_number,
            role=u.role,
        )
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

    collaboration = get_or_create_collaboration(db, sender.id, data.recipient_id)
    if collaboration.state in {CollaborationState.REQUESTED, CollaborationState.ACTIVE}:
        # Nothing to ask for: they are already talking, or already asked.
        raise AlreadyCollaboratingError
    collaboration.state = CollaborationState.REQUESTED

    request = CollaborationRequest(
        collaboration_id=collaboration.id,
        sender_id=sender.id,
        recipient_id=data.recipient_id,
        project_id=data.project_id,
        message=data.message,
    )
    db.add(request)
    try:
        db.flush()
        EVENT_BUS.publish(
            db,
            Event(
                name=EventName.COLLABORATION_REQUESTED,
                actor_id=sender.id,
                payload={
                    "recipient_id": request.recipient_id,
                    "request_id": request.id,
                    "sender_name": sender.full_name,
                },
            ),
        )
        # The unique constraint on the pair is the real guard: two concurrent
        # sends, in either direction, cannot both create a relationship.
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicatePendingError from exc
    db.refresh(request)
    return _to_reads(db, sender, [request])[0]


def get_or_create_collaboration(db: Session, one: uuid.UUID, other: uuid.UUID) -> Collaboration:
    """The pair's relationship row, creating it the first time they interact.

    Normalised, so asking for {a,b} and {b,a} returns the same row -- which is
    what stops two people holding simultaneous requests to each other.
    """
    user_a, user_b = normalise_pair(one, other)
    collaboration = db.execute(
        select(Collaboration).where(
            Collaboration.user_a_id == user_a, Collaboration.user_b_id == user_b
        )
    ).scalar_one_or_none()
    if collaboration is None:
        collaboration = Collaboration(user_a_id=user_a, user_b_id=user_b)
        db.add(collaboration)
        db.flush()
    return collaboration


#: Where a request's outcome leaves the pair.
_STATE_AFTER: dict[CollaborationStatus, CollaborationState] = {
    CollaborationStatus.ACCEPTED: CollaborationState.ACTIVE,
    # Declining or cancelling leaves no relationship, so either of them may
    # ask again -- it was a question, and the answer was no.
    CollaborationStatus.DECLINED: CollaborationState.NONE,
    CollaborationStatus.CANCELLED: CollaborationState.NONE,
    CollaborationStatus.ENDED: CollaborationState.ENDED,
}


def state_between(db: Session, viewer: User, other_id: uuid.UUID) -> CollaborationSummary:
    """What the two of them are to each other, and what to do about it.

    One query behind the button, so the interface never offers to start
    something that already exists.
    """
    user_a, user_b = normalise_pair(viewer.id, other_id)
    collaboration = db.execute(
        select(Collaboration).where(
            Collaboration.user_a_id == user_a, Collaboration.user_b_id == user_b
        )
    ).scalar_one_or_none()
    if collaboration is None:
        return CollaborationSummary(state=CollaborationState.NONE)

    live = (
        db.execute(
            select(CollaborationRequest)
            .where(
                CollaborationRequest.collaboration_id == collaboration.id,
                CollaborationRequest.status == CollaborationStatus.PENDING,
            )
            .order_by(CollaborationRequest.created_at.desc())
        )
        .scalars()
        .first()
    )
    conversation_id = db.execute(
        select(Conversation.id).where(Conversation.collaboration_id == collaboration.id)
    ).scalar_one_or_none()

    return CollaborationSummary(
        state=collaboration.state,
        request_id=live.id if live is not None else None,
        i_sent_it=live.sender_id == viewer.id if live is not None else None,
        conversation_id=conversation_id,
    )


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


def _open_thread_if_possible(db: Session, collaboration: Collaboration) -> None:
    """Give the accepted request a thread, but never at the cost of the answer.

    Chat is additive. Accepting a collaboration is the older, more important
    act, and it must not fail because the messages layer cannot -- which is
    exactly what happened on the deployed instance, where the code shipped
    before its migration and every acceptance answered 500. The savepoint
    keeps the failure from poisoning the surrounding transaction, so the
    acceptance still commits and the thread can be opened later.
    """
    try:
        with db.begin_nested():
            messages_service.open_for_collaboration(db, collaboration)
    except SQLAlchemyError:
        logger.exception(
            "Could not open a conversation for collaboration %s; the request is "
            "still accepted. Have migrations 0019-0021 run on this database?",
            collaboration.id,
        )


def respond(
    db: Session, actor: User, request_id: uuid.UUID, target: CollaborationStatus
) -> CollaborationRead:
    request = _load(db, actor, request_id)
    party: Actor = "sender" if request.sender_id == actor.id else "recipient"
    assert_transition(request.status, target, party)
    request.status = target
    request.responded_at = datetime.now(UTC)
    collaboration = db.get(Collaboration, request.collaboration_id)
    assert collaboration is not None
    collaboration.state = _STATE_AFTER[target]

    if target is CollaborationStatus.ACCEPTED:
        # Saying yes is what creates somewhere to talk. Nothing a client sends
        # can open a thread, so there is no channel to anyone who hasn't
        # agreed to one (ADR 0022).
        db.flush()
        _open_thread_if_possible(db, collaboration)
    # Tell the other party what happened.
    other_party = request.sender_id if party == "recipient" else request.recipient_id
    EVENT_BUS.publish(
        db,
        Event(
            name=EventName.COLLABORATION_RESPONDED,
            actor_id=actor.id,
            payload={
                "recipient_id": other_party,
                "request_id": request.id,
                "responder_name": actor.full_name,
                "status": target.value,
            },
        ),
    )
    db.commit()
    db.refresh(request)
    return _to_reads(db, actor, [request])[0]
