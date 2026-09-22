"""Creating and reading notifications.

Notifications are strictly per-user: every query is filtered by the caller's
own id, so there is no way to read someone else's.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.notifications.channels import Channel, InAppChannel
from app.modules.notifications.models import Notification, NotificationType
from app.modules.notifications.schemas import NotificationList, NotificationRead
from app.modules.users.models import User

DEFAULT_CHANNELS: tuple[Channel, ...] = (InAppChannel(),)


class NotificationNotFoundError(Exception):
    """No such notification for this user."""


def notify(
    db: Session,
    *,
    user_id: uuid.UUID,
    notification_type: NotificationType,
    payload: dict[str, Any],
    dedupe_key: str | None = None,
    channels: tuple[Channel, ...] = DEFAULT_CHANNELS,
) -> Notification | None:
    """Fan one notification out to the configured channels.

    Runs in the caller's transaction, so a notification and the action that
    caused it commit together.
    """
    created: Notification | None = None
    for channel in channels:
        result = channel.send(
            db,
            user_id=user_id,
            notification_type=notification_type,
            payload=payload,
            dedupe_key=dedupe_key,
        )
        created = created or result
    return created


def list_notifications(
    db: Session, user: User, *, unread_only: bool = False, limit: int = 50
) -> NotificationList:
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    rows = db.execute(query.order_by(Notification.created_at.desc()).limit(limit)).scalars().all()
    unread = db.execute(
        select(func.count()).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    ).scalar_one()
    return NotificationList(
        unread_count=int(unread),
        items=[
            NotificationRead(
                id=row.id,
                notification_type=row.notification_type,
                payload=row.payload,
                read_at=row.read_at,
                created_at=row.created_at,
            )
            for row in rows
        ],
    )


def mark_read(db: Session, user: User, notification_id: uuid.UUID) -> NotificationRead:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise NotificationNotFoundError
    if notification.read_at is None:
        notification.read_at = func.now()
        db.commit()
        db.refresh(notification)
    return NotificationRead(
        id=notification.id,
        notification_type=notification.notification_type,
        payload=notification.payload,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


def mark_all_read(db: Session, user: User) -> int:
    """Marks every unread notification read; returns how many changed."""
    unread = list(
        db.execute(
            select(Notification.id).where(
                Notification.user_id == user.id, Notification.read_at.is_(None)
            )
        ).scalars()
    )
    if unread:
        db.execute(
            update(Notification).where(Notification.id.in_(unread)).values(read_at=func.now())
        )
        db.commit()
    return len(unread)
