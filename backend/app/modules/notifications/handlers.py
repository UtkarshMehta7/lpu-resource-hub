"""Event subscribers that turn domain events into notifications.

Registered once at startup (`app/main.py`). Each handler decides *who* hears
about an event; the payload carries what the UI needs to render a line and a
link, so reading the list is a single query.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.events import EVENT_BUS, Event, EventBus, EventName
from app.modules.notifications.models import NotificationType
from app.modules.notifications.service import notify


def _on_application_submitted(db: Session, event: Event) -> None:
    notify(
        db,
        user_id=event.payload["recipient_id"],
        notification_type=NotificationType.APPLICATION_RECEIVED,
        payload={
            "application_id": str(event.payload["application_id"]),
            "opportunity_id": str(event.payload["opportunity_id"]),
            "opportunity_title": event.payload["opportunity_title"],
            "applicant_name": event.payload["applicant_name"],
        },
    )


def _on_application_decided(db: Session, event: Event) -> None:
    notify(
        db,
        user_id=event.payload["recipient_id"],
        notification_type=NotificationType.APPLICATION_DECIDED,
        payload={
            "application_id": str(event.payload["application_id"]),
            "opportunity_id": str(event.payload["opportunity_id"]),
            "opportunity_title": event.payload["opportunity_title"],
            "status": event.payload["status"],
            "note": event.payload.get("note"),
        },
    )


def _on_collaboration_requested(db: Session, event: Event) -> None:
    notify(
        db,
        user_id=event.payload["recipient_id"],
        notification_type=NotificationType.COLLABORATION_REQUEST,
        payload={
            "request_id": str(event.payload["request_id"]),
            "sender_name": event.payload["sender_name"],
        },
    )


def _on_collaboration_responded(db: Session, event: Event) -> None:
    notify(
        db,
        user_id=event.payload["recipient_id"],
        notification_type=NotificationType.COLLABORATION_RESPONSE,
        payload={
            "request_id": str(event.payload["request_id"]),
            "responder_name": event.payload["responder_name"],
            "status": event.payload["status"],
        },
    )


def _on_booking_decided(db: Session, event: Event) -> None:
    notify(
        db,
        user_id=event.payload["recipient_id"],
        notification_type=NotificationType.BOOKING_DECIDED,
        payload={
            "booking_id": str(event.payload["booking_id"]),
            "equipment_id": str(event.payload["equipment_id"]),
            "equipment_name": event.payload["equipment_name"],
            "status": event.payload["status"],
            "note": event.payload.get("note"),
        },
    )


def _on_project_reviewed(db: Session, event: Event) -> None:
    notify(
        db,
        user_id=event.payload["recipient_id"],
        notification_type=NotificationType.PROJECT_REVIEWED,
        payload={
            "project_id": str(event.payload["project_id"]),
            "project_title": event.payload["project_title"],
            "status": event.payload["status"],
            "comment": event.payload.get("comment"),
        },
    )


def _on_profile_verified(db: Session, event: Event) -> None:
    notify(
        db,
        user_id=event.payload["recipient_id"],
        notification_type=NotificationType.PROFILE_VERIFIED,
        payload={"status": event.payload["status"], "comment": event.payload.get("comment")},
    )


def _on_opportunity_published(db: Session, event: Event) -> None:
    # Imported here: matching reads the recommender, which imports far more
    # than a handler module should at import time.
    from app.modules.notifications.matching import notify_relevant_users

    notify_relevant_users(db, event.payload["opportunity_id"])


def register_notification_handlers(bus: EventBus = EVENT_BUS) -> None:
    bus.subscribe(EventName.APPLICATION_SUBMITTED, _on_application_submitted)
    bus.subscribe(EventName.APPLICATION_DECIDED, _on_application_decided)
    bus.subscribe(EventName.COLLABORATION_REQUESTED, _on_collaboration_requested)
    bus.subscribe(EventName.COLLABORATION_RESPONDED, _on_collaboration_responded)
    bus.subscribe(EventName.BOOKING_DECIDED, _on_booking_decided)
    bus.subscribe(EventName.PROJECT_REVIEWED, _on_project_reviewed)
    bus.subscribe(EventName.PROFILE_VERIFIED, _on_profile_verified)
    bus.subscribe(EventName.OPPORTUNITY_PUBLISHED, _on_opportunity_published)
