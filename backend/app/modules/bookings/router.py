"""Booking endpoints, mounted under /api/v1.

404 when the caller isn't a party to the booking (owner, scoped coordinator
or admin), 403 when they are but may not take that action, 409 when the
action isn't valid from the current status -- including the one that
matters most: an approval that would overlap an existing approved booking.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import client_ip
from app.db.session import get_db
from app.modules.bookings import service
from app.modules.bookings.models import BookingStatus
from app.modules.bookings.policies import InvalidTransitionError, WrongActorError
from app.modules.bookings.schemas import (
    AvailabilityRead,
    BookingCreate,
    BookingDecision,
    BookingRead,
)
from app.modules.users.models import User

router = APIRouter(tags=["bookings"])

CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
Approver = Annotated[User, Depends(require_permission(Permission.BOOKING_APPROVE))]

_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    service.BookingNotFoundError: (status.HTTP_404_NOT_FOUND, "Booking not found."),
    service.EquipmentNotFoundError: (status.HTTP_404_NOT_FOUND, "Equipment not found."),
    WrongActorError: (status.HTTP_403_FORBIDDEN, "You can't take that action on this booking."),
    service.StudentsNotAllowedError: (
        status.HTTP_403_FORBIDDEN,
        "This equipment isn't available to students.",
    ),
    service.OverlapError: (
        status.HTTP_409_CONFLICT,
        "That slot is already taken by an approved booking.",
    ),
    service.EquipmentUnavailableError: (
        status.HTTP_409_CONFLICT,
        "This equipment is under maintenance or retired.",
    ),
    InvalidTransitionError: (
        status.HTTP_409_CONFLICT,
        "That action isn't allowed while the booking is in its current status.",
    ),
    service.AlreadyStartedError: (
        status.HTTP_409_CONFLICT,
        "A booking can only be cancelled before it starts.",
    ),
    service.TooLongError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "That period is longer than this equipment allows.",
    ),
    service.TooSoonError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "This equipment needs more notice than that.",
    ),
    service.InThePastError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Bookings can't start in the past.",
    ),
}


@contextmanager
def _domain_errors() -> Iterator[None]:
    try:
        yield
    except tuple(_ERROR_MAP) as exc:
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from exc


@router.get("/equipment/{equipment_id}/availability", response_model=AvailabilityRead)
def read_availability(
    equipment_id: uuid.UUID,
    db: DbSession,
    viewer: CurrentUser,
    date_from: Annotated[datetime, Query(alias="from")],
    date_to: Annotated[datetime, Query(alias="to")],
) -> AvailabilityRead:
    """Approved bookings in a window, plus the equipment's booking rules.

    Only the periods are returned -- who holds a slot is not public.
    """
    with _domain_errors():
        return service.availability(db, viewer, equipment_id, date_from, date_to)


@router.post("/bookings", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
def create_booking(data: BookingCreate, db: DbSession, user: CurrentUser) -> BookingRead:
    with _domain_errors():
        return service.create_booking(db, user, data)


@router.get("/me/bookings", response_model=list[BookingRead])
def read_my_bookings(
    db: DbSession,
    user: CurrentUser,
    status_filter: Annotated[BookingStatus | None, Query(alias="status")] = None,
) -> list[BookingRead]:
    return service.my_bookings(db, user, status_filter)


@router.get("/coordinator/booking-queue", response_model=list[BookingRead])
def read_booking_queue(db: DbSession, approver: Approver) -> list[BookingRead]:
    return service.approval_queue(db, approver)


@router.get("/bookings/{booking_id}", response_model=BookingRead)
def read_booking(booking_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BookingRead:
    with _domain_errors():
        return service.get_booking(db, user, booking_id)


@router.post("/bookings/{booking_id}/approve", response_model=BookingRead)
def approve_booking(
    booking_id: uuid.UUID,
    data: BookingDecision,
    request: Request,
    db: DbSession,
    approver: Approver,
) -> BookingRead:
    with _domain_errors():
        return service.approve_booking(db, approver, booking_id, data.note, ip=client_ip(request))


@router.post("/bookings/{booking_id}/reject", response_model=BookingRead)
def reject_booking(
    booking_id: uuid.UUID,
    data: BookingDecision,
    request: Request,
    db: DbSession,
    approver: Approver,
) -> BookingRead:
    with _domain_errors():
        return service.reject_booking(db, approver, booking_id, data.note, ip=client_ip(request))


@router.post("/bookings/{booking_id}/cancel", response_model=BookingRead)
def cancel_booking(
    booking_id: uuid.UUID, request: Request, db: DbSession, user: CurrentUser
) -> BookingRead:
    with _domain_errors():
        return service.cancel_booking(db, user, booking_id, ip=client_ip(request))


@router.post("/bookings/{booking_id}/complete", response_model=BookingRead)
def complete_booking(
    booking_id: uuid.UUID, request: Request, db: DbSession, user: CurrentUser
) -> BookingRead:
    """Marks a finished booking as completed (owner or approver, after it ends)."""
    with _domain_errors():
        return service.complete_booking(db, user, booking_id, ip=client_ip(request))
