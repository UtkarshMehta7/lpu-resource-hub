"""Notification endpoints, mounted under /api/v1/me."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.notifications import service
from app.modules.notifications.schemas import NotificationList, NotificationRead
from app.modules.users.models import User

router = APIRouter(prefix="/me", tags=["notifications"])

CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/notifications", response_model=NotificationList)
def read_notifications(
    db: DbSession, user: CurrentUser, unread_only: bool = False
) -> NotificationList:
    """Your own notifications, newest first, with the unread count for the bell."""
    return service.list_notifications(db, user, unread_only=unread_only)


@router.post("/notifications/read-all", response_model=dict[str, int])
def mark_all_notifications_read(db: DbSession, user: CurrentUser) -> dict[str, int]:
    return {"marked_read": service.mark_all_read(db, user)}


@router.post("/notifications/{notification_id}/read", response_model=NotificationRead)
def mark_notification_read(
    notification_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> NotificationRead:
    try:
        return service.mark_read(db, user, notification_id)
    except service.NotificationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found."
        ) from exc
