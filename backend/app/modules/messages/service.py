"""Conversation threads: opening them, reading them, writing to them.

Threads are never created by a client. They appear as a consequence of
something else succeeding -- a collaboration request being accepted, a project
existing -- so there is no "create conversation" endpoint to secure, and no way
to conjure a channel to someone who has not agreed to one (ADR 0022).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.core.events import EVENT_BUS, Event, EventName
from app.modules.collaborations.models import CollaborationRequest, CollaborationStatus
from app.modules.messages.models import Conversation, ConversationParticipant, Message
from app.modules.messages.policies import ThreadNotFoundError, assert_participant
from app.modules.messages.schemas import (
    ConversationRead,
    MessagePage,
    MessageRead,
    Participant,
    SubjectKind,
)
from app.modules.notifications.models import Notification
from app.modules.projects.models import Project, ProjectMember
from app.modules.users.models import User

#: How much of a message the conversation list shows.
PREVIEW_LENGTH = 120
#: Default page size when walking a thread.
PAGE_SIZE = 50


class MessageTooLongError(Exception):
    """Guarded by the schema as well; kept so the service stands alone."""


# --------------------------------------------------------------- opening threads


def open_for_collaboration(db: Session, request: CollaborationRequest) -> Conversation | None:
    """Give an accepted request somewhere to continue.

    Called when a request is accepted, not when it is sent: a pending request
    is a question, and the answer may be no. Idempotent -- accepting is a
    single transition, but a retry must not produce a second thread.
    """
    if request.status is not CollaborationStatus.ACCEPTED:
        return None
    existing = db.execute(
        select(Conversation).where(Conversation.collaboration_request_id == request.id)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    conversation = Conversation(collaboration_request_id=request.id)
    db.add(conversation)
    db.flush()
    _add_participants(db, conversation.id, [request.sender_id, request.recipient_id])
    return conversation


def open_project_thread(db: Session, actor: User, project_id: uuid.UUID) -> ConversationRead:
    """Open the team's thread, or return it if somebody already did.

    The team is the owner plus the members, read from the database. Anyone
    else gets ThreadNotFoundError rather than a refusal: whether a project has
    a thread is the team's business.
    """
    project = db.get(Project, project_id)
    if project is None:
        raise ThreadNotFoundError
    member_ids = set(
        db.execute(select(ProjectMember.user_id).where(ProjectMember.project_id == project_id))
        .scalars()
        .all()
    )
    if actor.id != project.owner_id and actor.id not in member_ids:
        raise ThreadNotFoundError

    conversation = open_for_project(db, project)
    db.commit()
    return get_conversation(db, actor, conversation.id)


def open_for_project(db: Session, project: Project) -> Conversation:
    """The team's thread. Created on first use rather than with the project,
    so a draft nobody has opened does not carry an empty thread around."""
    existing = db.execute(
        select(Conversation).where(Conversation.project_id == project.id)
    ).scalar_one_or_none()
    if existing is not None:
        sync_project_participants(db, project.id)
        return existing

    conversation = Conversation(project_id=project.id)
    db.add(conversation)
    db.flush()
    sync_project_participants(db, project.id)
    return conversation


def _add_participants(db: Session, conversation_id: uuid.UUID, user_ids: list[uuid.UUID]) -> None:
    present = set(
        db.execute(
            select(ConversationParticipant.user_id).where(
                ConversationParticipant.conversation_id == conversation_id
            )
        )
        .scalars()
        .all()
    )
    for user_id in user_ids:
        if user_id not in present:
            db.add(ConversationParticipant(conversation_id=conversation_id, user_id=user_id))
    db.flush()


def sync_project_participants(db: Session, project_id: uuid.UUID) -> None:
    """Membership of a project thread follows membership of the project.

    Someone removed from the team loses the thread; their messages stay where
    they are, still attributed. The conversation is a record of what was said,
    not a possession of whoever is currently on the team.
    """
    conversation = db.execute(
        select(Conversation).where(Conversation.project_id == project_id)
    ).scalar_one_or_none()
    if conversation is None:
        return

    owner_id = db.execute(select(Project.owner_id).where(Project.id == project_id)).scalar_one()
    member_ids = set(
        db.execute(select(ProjectMember.user_id).where(ProjectMember.project_id == project_id))
        .scalars()
        .all()
    )
    should_be = member_ids | {owner_id}

    current = {
        row.user_id: row
        for row in db.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation.id
            )
        )
        .scalars()
        .all()
    }
    for user_id in should_be - set(current):
        db.add(ConversationParticipant(conversation_id=conversation.id, user_id=user_id))
    for user_id in set(current) - should_be:
        db.delete(current[user_id])
    db.flush()


# ------------------------------------------------------------------- reading


@dataclass(frozen=True, slots=True)
class Cursor:
    """A keyset position in a thread: everything after (created_at, id).

    Not an offset. A message arriving between two polls shifts every offset by
    one, which would silently skip a message; a keyset cannot.
    """

    created_at: datetime
    message_id: uuid.UUID

    def encode(self) -> str:
        return f"{self.created_at.isoformat()}|{self.message_id}"

    @classmethod
    def decode(cls, raw: str) -> Cursor | None:
        timestamp, _, identifier = raw.partition("|")
        try:
            return cls(datetime.fromisoformat(timestamp), uuid.UUID(identifier))
        except ValueError:
            # A malformed cursor means "start from the beginning", never an
            # error: a stale client should recover by itself.
            return None


def _participant_rows(
    db: Session, conversation_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[User]]:
    if not conversation_ids:
        return {}
    rows = db.execute(
        select(ConversationParticipant.conversation_id, User)
        .join(User, User.id == ConversationParticipant.user_id)
        .where(ConversationParticipant.conversation_id.in_(conversation_ids))
        .order_by(User.full_name)
    ).all()
    grouped: dict[uuid.UUID, list[User]] = {}
    for conversation_id, user in rows:
        grouped.setdefault(conversation_id, []).append(user)
    return grouped


def _title_for(
    db: Session, conversation: Conversation, participants: list[User], viewer: User
) -> tuple[SubjectKind, uuid.UUID, str]:
    if conversation.project_id is not None:
        title = db.execute(
            select(Project.title).where(Project.id == conversation.project_id)
        ).scalar_one_or_none()
        return SubjectKind.PROJECT, conversation.project_id, title or "Project"
    # A one-to-one thread is named after the other person, not after itself.
    others = [person for person in participants if person.id != viewer.id]
    name = others[0].full_name if others else "Conversation"
    assert conversation.collaboration_request_id is not None
    return SubjectKind.COLLABORATION, conversation.collaboration_request_id, name


def _unread_counts(
    db: Session, viewer: User, conversation_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not conversation_ids:
        return {}
    rows = db.execute(
        select(Message.conversation_id, func.count())
        .join(
            ConversationParticipant,
            (ConversationParticipant.conversation_id == Message.conversation_id)
            & (ConversationParticipant.user_id == viewer.id),
        )
        .where(
            Message.conversation_id.in_(conversation_ids),
            # Their own messages are never unread to them.
            Message.sender_id != viewer.id,
            or_(
                ConversationParticipant.last_read_at.is_(None),
                Message.created_at > ConversationParticipant.last_read_at,
            ),
        )
        .group_by(Message.conversation_id)
    ).all()
    return {conversation_id: count for conversation_id, count in rows}


def _previews(db: Session, conversation_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """The newest visible message per thread, truncated.

    A hidden message leaves no preview: the list is not a way to read around
    a moderator's decision.
    """
    if not conversation_ids:
        return {}
    newest = (
        select(
            Message.conversation_id,
            func.max(Message.created_at).label("created_at"),
        )
        .where(Message.conversation_id.in_(conversation_ids), Message.hidden_at.is_(None))
        .group_by(Message.conversation_id)
        .subquery()
    )
    rows = db.execute(
        select(Message.conversation_id, Message.body).join(
            newest,
            (Message.conversation_id == newest.c.conversation_id)
            & (Message.created_at == newest.c.created_at),
        )
    ).all()
    return {
        conversation_id: body[:PREVIEW_LENGTH] + ("…" if len(body) > PREVIEW_LENGTH else "")
        for conversation_id, body in rows
    }


def list_conversations(db: Session, viewer: User) -> list[ConversationRead]:
    """Every thread this person takes part in, most recent activity first.

    A thread with no messages yet sorts by when it opened, so accepting a
    request puts it at the top where the person expects to find it.
    """
    conversations = (
        db.execute(
            select(Conversation)
            .join(
                ConversationParticipant,
                ConversationParticipant.conversation_id == Conversation.id,
            )
            .where(ConversationParticipant.user_id == viewer.id)
            .order_by(func.coalesce(Conversation.last_message_at, Conversation.created_at).desc())
        )
        .scalars()
        .all()
    )
    ids = [conversation.id for conversation in conversations]
    participants = _participant_rows(db, ids)
    unread = _unread_counts(db, viewer, ids)
    previews = _previews(db, ids)

    reads: list[ConversationRead] = []
    for conversation in conversations:
        people = participants.get(conversation.id, [])
        kind, subject_id, title = _title_for(db, conversation, people, viewer)
        reads.append(
            ConversationRead(
                id=conversation.id,
                subject_kind=kind,
                subject_id=subject_id,
                title=title,
                participants=[
                    Participant(
                        user_id=person.id,
                        full_name=person.full_name,
                        registration_number=person.registration_number,
                        role=person.role,
                    )
                    for person in people
                ],
                unread_count=unread.get(conversation.id, 0),
                last_message_at=conversation.last_message_at,
                preview=previews.get(conversation.id),
                created_at=conversation.created_at,
            )
        )
    return reads


def get_conversation(db: Session, viewer: User, conversation_id: uuid.UUID) -> ConversationRead:
    assert_participant(db, conversation_id, viewer)
    for conversation in list_conversations(db, viewer):
        if conversation.id == conversation_id:
            return conversation
    raise ThreadNotFoundError


def read_messages(
    db: Session,
    viewer: User,
    conversation_id: uuid.UUID,
    *,
    after: str | None = None,
    limit: int = PAGE_SIZE,
) -> MessagePage:
    assert_participant(db, conversation_id, viewer)

    query = (
        select(Message, User)
        .join(User, User.id == Message.sender_id)
        .where(Message.conversation_id == conversation_id)
    )
    cursor = Cursor.decode(after) if after else None
    if cursor is not None:
        # Row-value comparison, so a message sharing a timestamp with the
        # cursor is not skipped and not repeated.
        query = query.where(
            tuple_(Message.created_at, Message.id) > (cursor.created_at, cursor.message_id)
        )
    rows = db.execute(query.order_by(Message.created_at, Message.id).limit(limit)).all()

    items = [
        MessageRead(
            id=message.id,
            conversation_id=message.conversation_id,
            sender_id=message.sender_id,
            sender_name=sender.full_name,
            sender_registration_number=sender.registration_number,
            body=None if message.hidden_at is not None else message.body,
            hidden=message.hidden_at is not None,
            created_at=message.created_at,
        )
        for message, sender in rows
    ]
    next_after = Cursor(rows[-1][0].created_at, rows[-1][0].id).encode() if rows else after
    return MessagePage(items=items, next_after=next_after)


# ------------------------------------------------------------------- writing


def send_message(db: Session, sender: User, conversation_id: uuid.UUID, body: str) -> MessageRead:
    assert_participant(db, conversation_id, sender)

    message = Message(conversation_id=conversation_id, sender_id=sender.id, body=body.strip())
    db.add(message)
    db.flush()

    conversation = db.get(Conversation, conversation_id)
    assert conversation is not None
    conversation.last_message_at = message.created_at

    # Sending is also reading: your own message must not come back unread.
    mark_read(db, sender, conversation_id, commit=False)

    for recipient_id in _others(db, conversation_id, sender.id):
        EVENT_BUS.publish(
            db,
            Event(
                name=EventName.MESSAGE_SENT,
                actor_id=sender.id,
                payload={
                    "recipient_id": recipient_id,
                    "conversation_id": conversation_id,
                    "sender_name": sender.full_name,
                    "preview": body.strip()[:PREVIEW_LENGTH],
                },
            ),
        )
    db.commit()
    db.refresh(message)
    return MessageRead(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        sender_name=sender.full_name,
        sender_registration_number=sender.registration_number,
        body=message.body,
        hidden=False,
        created_at=message.created_at,
    )


def _others(db: Session, conversation_id: uuid.UUID, actor_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        db.execute(
            select(ConversationParticipant.user_id).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id != actor_id,
                ConversationParticipant.muted.is_(False),
            )
        )
        .scalars()
        .all()
    )


def mark_read(
    db: Session, viewer: User, conversation_id: uuid.UUID, *, commit: bool = True
) -> None:
    assert_participant(db, conversation_id, viewer)
    participant = db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == viewer.id,
        )
    ).scalar_one()
    participant.last_read_at = datetime.now(UTC)

    # Clear the "you have a message" notice for this thread. Two jobs in one:
    # the bell stops pointing at something already read, and the dedupe key it
    # occupied is freed, so the next message said here is announced again
    # (notifications/handlers.py::_on_message_sent).
    db.execute(
        delete(Notification).where(
            Notification.user_id == viewer.id,
            Notification.dedupe_key == f"conversation:{conversation_id}",
        )
    )
    if commit:
        db.commit()


def unread_total(db: Session, viewer: User) -> int:
    """One number for the navigation badge, without building every thread."""
    ids = list(
        db.execute(
            select(ConversationParticipant.conversation_id).where(
                ConversationParticipant.user_id == viewer.id
            )
        )
        .scalars()
        .all()
    )
    return sum(_unread_counts(db, viewer, ids).values())


def count_messages_sent(db: Session, user_id: uuid.UUID) -> int:
    """For DeletionImpact: deleting an account takes its messages with it."""
    return db.execute(
        select(func.count()).select_from(Message).where(Message.sender_id == user_id)
    ).scalar_one()
