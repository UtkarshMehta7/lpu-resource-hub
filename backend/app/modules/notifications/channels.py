"""Delivery channels for notifications.

In-app is the only real channel for now. EmailChannel is a stub that logs
what it would send: it keeps the seam honest (the service never assumes a
single channel) without pretending email works.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.modules.notifications.models import Notification, NotificationType

logger = logging.getLogger(__name__)


class Channel(Protocol):
    def send(
        self,
        db: Session,
        *,
        user_id: Any,
        notification_type: NotificationType,
        payload: dict[str, Any],
        dedupe_key: str | None,
    ) -> Notification | None: ...


class InAppChannel:
    """Writes a notification row in the caller's transaction."""

    def send(
        self,
        db: Session,
        *,
        user_id: Any,
        notification_type: NotificationType,
        payload: dict[str, Any],
        dedupe_key: str | None,
    ) -> Notification | None:
        if dedupe_key is not None:
            existing = db.execute(
                Notification.__table__.select().where(
                    Notification.user_id == user_id, Notification.dedupe_key == dedupe_key
                )
            ).first()
            if existing is not None:
                # Already told them; the partial unique index backs this up.
                return None
        notification = Notification(
            user_id=user_id,
            notification_type=notification_type,
            payload=payload,
            dedupe_key=dedupe_key,
        )
        db.add(notification)
        db.flush()
        return notification


class EmailChannel:
    """Stub: logs instead of sending. No SMTP, no paid service (zero cost)."""

    def send(
        self,
        db: Session,
        *,
        user_id: Any,
        notification_type: NotificationType,
        payload: dict[str, Any],
        dedupe_key: str | None,
    ) -> Notification | None:
        logger.info(
            "email(stub) to=%s type=%s payload=%s", user_id, notification_type.value, payload
        )
        return None
