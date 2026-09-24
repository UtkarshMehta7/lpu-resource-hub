"""Conversation thread endpoints, mounted under /api/v1.

404, never 403, for a thread you are not in: a 403 on a thread id would
confirm that two named people are talking, which is the one fact a private
thread exists to keep. 429 when sending faster than a person can type.

There is no endpoint that creates a thread. Threads appear when a
collaboration request is accepted or when a project team first opens one, so
there is no way to conjure a channel to somebody who has not agreed to one.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rate_limit import enforce_message_rate_limit
from app.db.session import get_db
from app.modules.messages import service
from app.modules.messages.policies import ThreadNotFoundError
from app.modules.messages.schemas import (
    ConversationRead,
    MessageCreate,
    MessagePage,
    MessageRead,
)
from app.modules.messages.service import PAGE_SIZE
from app.modules.users.models import User

router = APIRouter(tags=["messages"])

CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")


@router.get("/me/conversations", response_model=list[ConversationRead])
def list_my_conversations(db: DbSession, viewer: CurrentUser) -> list[ConversationRead]:
    """Every thread this person takes part in, most recent activity first."""
    return service.list_conversations(db, viewer)


@router.get("/me/conversations/unread-count", response_model=int)
def read_unread_total(db: DbSession, viewer: CurrentUser) -> int:
    """One number for the navigation badge. Cheap enough to poll."""
    return service.unread_total(db, viewer)


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
def read_conversation(
    conversation_id: uuid.UUID, db: DbSession, viewer: CurrentUser
) -> ConversationRead:
    try:
        return service.get_conversation(db, viewer, conversation_id)
    except ThreadNotFoundError as exc:
        raise _NOT_FOUND from exc


@router.get("/conversations/{conversation_id}/messages", response_model=MessagePage)
def read_conversation_messages(
    conversation_id: uuid.UUID,
    db: DbSession,
    viewer: CurrentUser,
    after: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = PAGE_SIZE,
) -> MessagePage:
    """One slice of a thread, oldest first.

    Poll by passing the previous response's `next_after` back as `after`: only
    what arrived since comes back, so an open thread costs one small query
    every few seconds rather than the whole history.
    """
    try:
        return service.read_messages(db, viewer, conversation_id, after=after, limit=limit)
    except ThreadNotFoundError as exc:
        raise _NOT_FOUND from exc


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
def post_message(
    conversation_id: uuid.UUID,
    data: MessageCreate,
    request: Request,
    db: DbSession,
    sender: CurrentUser,
) -> MessageRead:
    enforce_message_rate_limit(request, sender.id)
    try:
        return service.send_message(db, sender, conversation_id, data.body)
    except ThreadNotFoundError as exc:
        raise _NOT_FOUND from exc


@router.post("/conversations/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_conversation_read(conversation_id: uuid.UUID, db: DbSession, viewer: CurrentUser) -> None:
    """Move this person's read mark to now, and clear the thread's notice."""
    try:
        service.mark_read(db, viewer, conversation_id)
    except ThreadNotFoundError as exc:
        raise _NOT_FOUND from exc


@router.post(
    "/projects/{project_id}/conversation",
    response_model=ConversationRead,
    status_code=status.HTTP_200_OK,
)
def open_project_conversation(
    project_id: uuid.UUID, db: DbSession, actor: CurrentUser
) -> ConversationRead:
    """Open the team thread for a project, or return the existing one.

    Idempotent, so the button on the project page does not need to know
    whether anyone has opened it before. 404 for anyone not on the team --
    whether a project has a thread is the team's business.
    """
    try:
        return service.open_project_thread(db, actor, project_id)
    except ThreadNotFoundError as exc:
        raise _NOT_FOUND from exc
