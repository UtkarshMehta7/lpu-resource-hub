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
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import get_app_settings, get_current_user
from app.core.rate_limit import enforce_message_rate_limit
from app.db.session import get_db
from app.modules.messages import service
from app.modules.messages.models import MESSAGE_MAX_LENGTH
from app.modules.messages.policies import ThreadNotFoundError
from app.modules.messages.schemas import (
    ConversationRead,
    MessageCreate,
    MessagePage,
    MessageRead,
)
from app.modules.messages.service import PAGE_SIZE, ThreadClosedError
from app.modules.uploads import validation
from app.modules.users.models import User

router = APIRouter(tags=["messages"])

AppSettings = Annotated[Settings, Depends(get_app_settings)]
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
    except ThreadClosedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This collaboration has ended, so the conversation is read-only.",
        ) from exc


@router.post(
    "/conversations/{conversation_id}/attachments",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
def post_attachment(
    conversation_id: uuid.UUID,
    request: Request,
    db: DbSession,
    sender: CurrentUser,
    settings: AppSettings,
    file: Annotated[UploadFile, File(description="The file to share.")],
    caption: Annotated[str, Form(max_length=MESSAGE_MAX_LENGTH)] = "",
) -> MessageRead:
    """Share a file in a thread. It arrives as a message, with an optional
    caption, so it is subject to every rule an ordinary message is."""
    # Shares the message budget: both are "this account is putting things in
    # other people's threads", and a file costs more to carry than a line.
    enforce_message_rate_limit(request, sender.id)
    data = file.file.read(settings.upload_max_bytes + 1)
    try:
        return service.send_attachment(
            db,
            sender,
            conversation_id,
            data=data,
            filename=file.filename,
            caption=caption,
            max_bytes=settings.upload_max_bytes,
        )
    except ThreadNotFoundError as exc:
        raise _NOT_FOUND from exc
    except ThreadClosedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This collaboration has ended, so the conversation is read-only.",
        ) from exc
    except validation.EmptyFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That file is empty.",
        ) from exc
    except validation.FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"That file is larger than {exc.limit // (1024 * 1024)} MB. "
                "Share a link to it instead."
            ),
        ) from exc
    except validation.UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"That file type is not accepted. Allowed: {validation.ALLOWED_LABELS}.",
        ) from exc


@router.get(
    "/conversations/{conversation_id}/attachments/{attachment_id}",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
def download_attachment(
    conversation_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: DbSession,
    viewer: CurrentUser,
) -> Response:
    """The file itself, for a participant only.

    Always `Content-Disposition: attachment`: nothing shared in a thread is
    rendered in the browser on this origin, so an uploaded file cannot become
    a script running as the application. `private` caching for the same
    reason the thread is scoped -- a shared cache must not hold it.
    """
    try:
        attachment = service.read_attachment(db, viewer, conversation_id, attachment_id)
    except ThreadNotFoundError as exc:
        raise _NOT_FOUND from exc
    return Response(
        content=attachment.data,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{attachment.filename}"; '
                f"filename*=UTF-8''{quote(attachment.filename)}"
            ),
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


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
