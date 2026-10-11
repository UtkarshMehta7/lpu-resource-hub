"""Announcement endpoints, mounted under /api/v1.

Reading takes `get_current_user` and no permission: every signed-in role reads
the board. Posting takes `Permission.ANNOUNCEMENT_POST`. Which notices a
reader sees is `policies.visibility_filter`, applied in the service.

The order of the two failure answers matters and is the same order the patent
pipeline uses: a move that does NOT EXIST is 409 whoever asks (a published
notice cannot be edited by anybody, its author included), and a move that
exists but belongs to somebody else is 403. Checked the other way round, an
author would be told that editing their own published notice was merely above
their pay grade.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.deps import get_current_user
from app.core.pagination import Page, PageParams
from app.core.permissions import Permission, require_permission
from app.db.session import get_db
from app.modules.announcements import policies, service
from app.modules.announcements.schemas import (
    AnnouncementCreate,
    AnnouncementRead,
    AnnouncementUpdate,
    UnreadCount,
)
from app.modules.uploads import validation
from app.modules.users.models import User

router = APIRouter(tags=["announcements"])

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Poster = Annotated[User, Depends(require_permission(Permission.ANNOUNCEMENT_POST))]
AppSettings = Annotated[Settings, Depends(get_settings)]

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found.")


@contextmanager
def _domain_errors() -> Iterator[None]:
    try:
        yield
    except service.AnnouncementNotFoundError as exc:
        raise _NOT_FOUND from exc
    except service.WrongStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A published announcement cannot be changed. Withdraw it and post a correction."
            ),
        ) from exc
    except service.NotYoursError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This announcement was posted by somebody else.",
        ) from exc
    except policies.NoScopeToPostError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You have no department to announce to. "
                "Ask an administrator to set your coordinator scope."
            ),
        ) from exc


@router.get("/announcements", response_model=Page[AnnouncementRead])
def read_announcements(
    db: DbSession,
    viewer: CurrentUser,
    params: Annotated[PageParams, Depends()],
    q: str | None = None,
    unread_only: bool = False,
    mine: bool = False,
) -> Page[AnnouncementRead]:
    """The board: what has been announced to you, newest first."""
    return service.list_announcements(db, params, viewer, q=q, unread_only=unread_only, mine=mine)


@router.get("/announcements/unread-count", response_model=UnreadCount)
def read_unread_count(db: DbSession, viewer: CurrentUser) -> UnreadCount:
    """Drives the badge. Its own path, registered before `/{announcement_id}`.

    A nested literal loses to a path parameter registered first -- FastAPI
    matches in registration order, and "unread-count" would be parsed as a
    UUID. The same trap `/publications/duplicates` fell into.
    """
    return UnreadCount(unread=service.unread_count(db, viewer))


@router.post("/announcements", response_model=AnnouncementRead, status_code=status.HTTP_201_CREATED)
def create_announcement(data: AnnouncementCreate, db: DbSession, actor: Poster) -> AnnouncementRead:
    """Write a notice. It is a draft until published, and reaches nobody yet.

    The audience is not in the request: it is derived from the poster, so a
    coordinator addresses their own department and cannot name another.
    """
    with _domain_errors():
        return service.create_announcement(db, actor, data)


@router.get("/announcements/{announcement_id}", response_model=AnnouncementRead)
def read_announcement(
    announcement_id: uuid.UUID, db: DbSession, viewer: CurrentUser
) -> AnnouncementRead:
    with _domain_errors():
        return service.get_announcement(db, announcement_id, viewer)


@router.patch("/announcements/{announcement_id}", response_model=AnnouncementRead)
def update_announcement(
    announcement_id: uuid.UUID, data: AnnouncementUpdate, db: DbSession, actor: CurrentUser
) -> AnnouncementRead:
    with _domain_errors():
        return service.update_announcement(db, announcement_id, actor, data)


@router.post("/announcements/{announcement_id}/publish", response_model=AnnouncementRead)
def publish_announcement(
    announcement_id: uuid.UUID, db: DbSession, actor: CurrentUser
) -> AnnouncementRead:
    """Put it on the board. From here it is readable and no longer editable."""
    with _domain_errors():
        return service.publish_announcement(db, announcement_id, actor)


@router.post("/announcements/{announcement_id}/withdraw", response_model=AnnouncementRead)
def withdraw_announcement(
    announcement_id: uuid.UUID, db: DbSession, actor: CurrentUser
) -> AnnouncementRead:
    """Take it off the board. The author or an administrator."""
    with _domain_errors():
        return service.withdraw_announcement(db, announcement_id, actor)


@router.delete("/announcements/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_announcement(announcement_id: uuid.UUID, db: DbSession, actor: CurrentUser) -> None:
    with _domain_errors():
        service.delete_announcement(db, announcement_id, actor)


@router.post("/announcements/{announcement_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_announcement_read(announcement_id: uuid.UUID, db: DbSession, viewer: CurrentUser) -> None:
    with _domain_errors():
        service.mark_read(db, announcement_id, viewer)


@router.post(
    "/announcements/{announcement_id}/attachments",
    response_model=AnnouncementRead,
    status_code=status.HTTP_201_CREATED,
)
def add_attachment(
    announcement_id: uuid.UUID,
    db: DbSession,
    actor: CurrentUser,
    settings: AppSettings,
    file: Annotated[UploadFile, File(description="The file to attach.")],
) -> AnnouncementRead:
    """Attach a PDF, image or document to a draft."""
    data = file.file.read(settings.upload_max_bytes + 1)
    with _domain_errors():
        try:
            return service.add_attachment(
                db,
                announcement_id,
                actor,
                data=data,
                filename=file.filename,
                max_bytes=settings.upload_max_bytes,
            )
        except validation.EmptyFileError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="That file is empty."
            ) from exc
        except validation.FileTooLargeError as exc:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    f"That file is larger than {exc.limit // (1024 * 1024)} MB. Link to it instead."
                ),
            ) from exc
        except validation.UnsupportedFileTypeError as exc:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"That file type is not accepted. Allowed: {validation.ALLOWED_LABELS}.",
            ) from exc


@router.delete(
    "/announcements/{announcement_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_attachment(
    announcement_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: DbSession,
    actor: CurrentUser,
) -> None:
    with _domain_errors():
        service.remove_attachment(db, announcement_id, attachment_id, actor)


@router.get(
    "/announcements/{announcement_id}/attachments/{attachment_id}",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
def download_attachment(
    announcement_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: DbSession,
    viewer: CurrentUser,
) -> Response:
    """The file itself, for anyone the notice is addressed to.

    Always `Content-Disposition: attachment`: nothing uploaded here is
    rendered in the browser on this origin, so an attached file cannot become
    a script running as the application. The interface renders images from
    the fetched bytes instead, which keeps that guarantee.
    """
    with _domain_errors():
        attachment = service.read_attachment(db, announcement_id, attachment_id, viewer)
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


__all__ = ["router"]
