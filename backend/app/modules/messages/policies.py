"""Who may read and write in a thread.

One rule, stated once: you are a participant or the thread does not exist for
you. Not 403 -- 404. A 403 on a thread id would confirm that a conversation
between two named people is happening, which is exactly the fact the thread is
meant to keep between them.

Moderators are no exception. Seeing a reported message in the moderation queue
is not the same as being able to open the thread it came from, and only the
first is offered (ADR 0022).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.messages.models import ConversationParticipant
from app.modules.users.models import User


class ThreadNotFoundError(Exception):
    """No such thread, or none this person takes part in. The caller must not
    be able to tell those apart."""


def is_participant(db: Session, conversation_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return (
        db.execute(
            select(ConversationParticipant.user_id).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
            )
        ).first()
        is not None
    )


def assert_participant(db: Session, conversation_id: uuid.UUID, actor: User) -> None:
    """Read from the database every time.

    Membership changes while people are looking at the page -- a project member
    is removed, a request is cancelled -- so a token or a client-held id is
    never the authority on it.
    """
    if not is_participant(db, conversation_id, actor.id):
        raise ThreadNotFoundError
