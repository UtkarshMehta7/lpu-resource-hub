"""Equipment bookings: rules, approval and availability.

The booking rules (who may book, how long, how far ahead) live on the
equipment row and are checked here. Overlap is *not* checked here: the
EXCLUDE constraint in PostgreSQL is the only thing that decides it, so two
concurrent approvals can never both succeed.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql.ranges import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.audit import service as audit_service
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.bookings.policies import (
    CANCELLABLE,
    Actor,
    InvalidTransitionError,
    WrongActorError,
    assert_transition,
)
from app.modules.bookings.schemas import (
    AvailabilityRead,
    BookingCreate,
    BookingRead,
    BusySlot,
)
from app.modules.facilities.models import Equipment, Facility, MaintenanceStatus
from app.modules.facilities.policies import coordinator_department
from app.modules.facilities.service import EquipmentNotFoundError, load_equipment
from app.modules.users.models import User, UserRole

OVERLAP_CONSTRAINT = "no_overlapping_approved_bookings"


class BookingNotFoundError(Exception):
    """No such booking, or the caller may not know it exists."""


class EquipmentUnavailableError(Exception):
    """The equipment is under maintenance or retired."""


class StudentsNotAllowedError(Exception):
    """This equipment isn't bookable by students."""


class TooLongError(Exception):
    """The requested period exceeds the equipment's max_hours."""


class TooSoonError(Exception):
    """The request doesn't respect the equipment's minimum lead time."""


class InThePastError(Exception):
    """Bookings can't start in the past."""


class OverlapError(Exception):
    """Another approved booking already holds part of this slot."""


class AlreadyStartedError(Exception):
    """An in-progress or past booking can't be cancelled."""


def _now() -> datetime:
    return datetime.now(UTC)


def _period(booking: Booking) -> tuple[datetime, datetime]:
    lower = booking.period.lower
    upper = booking.period.upper
    assert lower is not None and upper is not None  # noqa: S101 - tstzrange is always bounded
    return lower, upper


def _to_reads(db: Session, bookings: Sequence[Booking]) -> list[BookingRead]:
    if not bookings:
        return []
    rows = db.execute(
        select(Equipment.id, Equipment.name, Facility.name)
        .join(Facility, Facility.id == Equipment.facility_id)
        .where(Equipment.id.in_({booking.equipment_id for booking in bookings}))
    ).all()
    equipment = {row[0]: (row[1], row[2]) for row in rows}
    names = {
        user_id: name
        for user_id, name in db.execute(
            select(User.id, User.full_name).where(
                User.id.in_({booking.user_id for booking in bookings})
            )
        ).all()
    }
    reads: list[BookingRead] = []
    for booking in bookings:
        starts_at, ends_at = _period(booking)
        equipment_name, facility_name = equipment.get(booking.equipment_id, ("", ""))
        reads.append(
            BookingRead(
                id=booking.id,
                equipment_id=booking.equipment_id,
                equipment_name=equipment_name,
                facility_name=facility_name,
                user_id=booking.user_id,
                user_name=names.get(booking.user_id, ""),
                starts_at=starts_at,
                ends_at=ends_at,
                purpose=booking.purpose,
                status=booking.status,
                decided_by=booking.decided_by,
                decided_at=booking.decided_at,
                decision_note=booking.decision_note,
                created_at=booking.created_at,
            )
        )
    return reads


def _assert_rules(user: User, equipment: Equipment, data: BookingCreate) -> None:
    if equipment.maintenance_status is not MaintenanceStatus.AVAILABLE:
        raise EquipmentUnavailableError
    if user.role is UserRole.STUDENT and not equipment.students_allowed:
        raise StudentsNotAllowedError
    now = _now()
    if data.starts_at < now:
        raise InThePastError
    if data.ends_at - data.starts_at > timedelta(hours=equipment.max_hours):
        raise TooLongError
    if data.starts_at - now < timedelta(hours=equipment.min_lead_hours):
        raise TooSoonError


def _is_overlap(error: IntegrityError) -> bool:
    return OVERLAP_CONSTRAINT in str(error.orig)


def create_booking(db: Session, user: User, data: BookingCreate) -> BookingRead:
    equipment = load_equipment(db, data.equipment_id)
    _assert_rules(user, equipment, data)

    booking = Booking(
        equipment_id=equipment.id,
        user_id=user.id,
        period=Range(data.starts_at, data.ends_at, bounds="[)"),
        purpose=data.purpose,
        # Equipment that needs no approval is booked outright -- but it still
        # goes through the same EXCLUDE constraint, so it can still lose a
        # race to someone else's slot.
        status=(BookingStatus.PENDING if equipment.requires_approval else BookingStatus.APPROVED),
    )
    if not equipment.requires_approval:
        booking.decided_at = _now()
    db.add(booking)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_overlap(exc):
            raise OverlapError from exc
        raise
    db.refresh(booking)
    return _to_reads(db, [booking])[0]


def _approver_department(db: Session, booking: Booking) -> uuid.UUID | None:
    return db.execute(
        select(Facility.department_id)
        .join(Equipment, Equipment.facility_id == Facility.id)
        .where(Equipment.id == booking.equipment_id)
    ).scalar_one_or_none()


def _actor_for(db: Session, user: User, booking: Booking) -> Actor | None:
    """How this user relates to the booking, or None if they can't see it."""
    if booking.user_id == user.id:
        return "owner"
    if user.role is UserRole.ADMIN:
        return "approver"
    scope = coordinator_department(user)
    if scope is not None and scope == _approver_department(db, booking):
        return "approver"
    return None


def _load_visible(db: Session, user: User, booking_id: uuid.UUID) -> tuple[Booking, Actor]:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise BookingNotFoundError
    actor = _actor_for(db, user, booking)
    if actor is None:
        raise BookingNotFoundError
    return booking, actor


def get_booking(db: Session, user: User, booking_id: uuid.UUID) -> BookingRead:
    booking, _ = _load_visible(db, user, booking_id)
    return _to_reads(db, [booking])[0]


def my_bookings(db: Session, user: User, status: BookingStatus | None = None) -> list[BookingRead]:
    query = select(Booking).where(Booking.user_id == user.id)
    if status is not None:
        query = query.where(Booking.status == status)
    rows = db.execute(query.order_by(Booking.created_at.desc())).scalars().all()
    return _to_reads(db, list(rows))


def approval_queue(db: Session, approver: User) -> list[BookingRead]:
    """Pending requests for equipment the approver is responsible for."""
    query = (
        select(Booking)
        .join(Equipment, Equipment.id == Booking.equipment_id)
        .join(Facility, Facility.id == Equipment.facility_id)
        .where(Booking.status == BookingStatus.PENDING)
    )
    if approver.role is not UserRole.ADMIN:
        scope = coordinator_department(approver)
        if scope is None:
            return []
        query = query.where(Facility.department_id == scope)
    rows = db.execute(query.order_by(Booking.created_at)).scalars().all()
    return _to_reads(db, list(rows))


def _decide(
    db: Session,
    user: User,
    booking_id: uuid.UUID,
    target: BookingStatus,
    note: str | None,
    *,
    ip: str | None,
) -> BookingRead:
    booking, actor = _load_visible(db, user, booking_id)
    assert_transition(booking.status, target, actor)

    if target is BookingStatus.CANCELLED and booking.status in CANCELLABLE:
        starts_at, _ = _period(booking)
        if starts_at <= _now():
            raise AlreadyStartedError
    if target is BookingStatus.COMPLETED:
        _, ends_at = _period(booking)
        if ends_at > _now():
            raise InvalidTransitionError

    before = booking.status
    booking.status = target
    if actor == "approver":
        booking.decided_by = user.id
        booking.decided_at = _now()
        booking.decision_note = note
        audit_service.record(
            db,
            actor_id=user.id,
            action=f"booking.{target.value}",
            entity_type="booking",
            entity_id=booking.id,
            before={"status": before.value},
            after={"status": target.value, "note": note},
            ip=ip,
        )
    try:
        # Approving is where the EXCLUDE constraint bites: several pending
        # requests may overlap, but only one of them can become approved.
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_overlap(exc):
            raise OverlapError from exc
        raise
    db.refresh(booking)
    return _to_reads(db, [booking])[0]


def approve_booking(
    db: Session, user: User, booking_id: uuid.UUID, note: str | None, *, ip: str | None
) -> BookingRead:
    return _decide(db, user, booking_id, BookingStatus.APPROVED, note, ip=ip)


def reject_booking(
    db: Session, user: User, booking_id: uuid.UUID, note: str | None, *, ip: str | None
) -> BookingRead:
    return _decide(db, user, booking_id, BookingStatus.REJECTED, note, ip=ip)


def cancel_booking(
    db: Session, user: User, booking_id: uuid.UUID, *, ip: str | None
) -> BookingRead:
    return _decide(db, user, booking_id, BookingStatus.CANCELLED, None, ip=ip)


def complete_booking(
    db: Session, user: User, booking_id: uuid.UUID, *, ip: str | None
) -> BookingRead:
    return _decide(db, user, booking_id, BookingStatus.COMPLETED, None, ip=ip)


def availability(
    db: Session, user: User, equipment_id: uuid.UUID, start: datetime, end: datetime
) -> AvailabilityRead:
    equipment = load_equipment(db, equipment_id)
    window = Range(start, end, bounds="[)")
    rows = (
        db.execute(
            select(Booking)
            .where(
                Booking.equipment_id == equipment.id,
                Booking.status == BookingStatus.APPROVED,
                Booking.period.op("&&")(func.tstzrange(window.lower, window.upper, "[)")),
            )
            .order_by(Booking.period)
        )
        .scalars()
        .all()
    )
    busy = []
    for booking in rows:
        starts_at, ends_at = _period(booking)
        busy.append(
            BusySlot(starts_at=starts_at, ends_at=ends_at, is_mine=booking.user_id == user.id)
        )
    return AvailabilityRead(
        equipment_id=equipment.id,
        maintenance_status=equipment.maintenance_status.value,
        students_allowed=equipment.students_allowed,
        requires_approval=equipment.requires_approval,
        max_hours=equipment.max_hours,
        min_lead_hours=equipment.min_lead_hours,
        busy=busy,
    )


__all__ = [
    "AlreadyStartedError",
    "BookingNotFoundError",
    "EquipmentNotFoundError",
    "EquipmentUnavailableError",
    "InThePastError",
    "InvalidTransitionError",
    "OverlapError",
    "StudentsNotAllowedError",
    "TooLongError",
    "TooSoonError",
    "WrongActorError",
    "approval_queue",
    "approve_booking",
    "availability",
    "cancel_booking",
    "complete_booking",
    "create_booking",
    "get_booking",
    "my_bookings",
    "reject_booking",
]
