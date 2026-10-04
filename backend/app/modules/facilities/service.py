"""Facility and equipment catalogue. Services never import FastAPI."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams
from app.modules.admin.models import Department
from app.modules.audit import service as audit_service
from app.modules.facilities.models import Equipment, Facility
from app.modules.facilities.policies import (
    assert_can_manage,
    assert_may_manage_facility,
    coordinator_department,
)
from app.modules.facilities.schemas import (
    CustodianAssign,
    CustodianCandidate,
    EquipmentCreate,
    EquipmentRead,
    EquipmentUpdate,
    FacilityCreate,
    FacilityRead,
    FacilityUpdate,
)
from app.modules.users.models import User, UserRole


class FacilityNotFoundError(Exception):
    """No such facility."""


class EquipmentNotFoundError(Exception):
    """No such equipment."""


class DuplicateFacilityError(Exception):
    """That department already has a facility with this name."""


class DepartmentRequiredError(Exception):
    """A coordinator's facility must belong to the department they oversee."""


class NotACustodianError(Exception):
    """Only a facility custodian can be made the custodian of a facility.

    Pointing the column at anybody else would leave a facility looking looked
    after by somebody who does not hold FACILITY_MANAGE at all -- a silent
    nothing rather than a refusal.
    """


class CustodianDepartmentError(Exception):
    """A custodian must belong to the department that runs the facility.

    Otherwise the department's coordinator cannot oversee the person looking
    after their own rooms, which is the "coordinator oversees nothing" bug in
    a new place.
    """


def _facility_reads(db: Session, facilities: Sequence[Facility]) -> list[FacilityRead]:
    if not facilities:
        return []
    counts: dict[uuid.UUID, int] = {
        facility_id: count
        for facility_id, count in db.execute(
            select(Equipment.facility_id, func.count())
            .where(Equipment.facility_id.in_([f.id for f in facilities]))
            .group_by(Equipment.facility_id)
        ).all()
    }
    department_ids = {f.department_id for f in facilities if f.department_id is not None}
    department_names: dict[uuid.UUID, str] = (
        {
            row.id: row.name
            for row in db.execute(
                select(Department).where(Department.id.in_(department_ids))
            ).scalars()
        }
        if department_ids
        else {}
    )
    custodian_ids = {f.custodian_id for f in facilities if f.custodian_id is not None}
    custodians: dict[uuid.UUID, User] = (
        {
            person.id: person
            for person in db.execute(select(User).where(User.id.in_(custodian_ids))).scalars()
        }
        if custodian_ids
        else {}
    )
    reads: list[FacilityRead] = []
    for facility in facilities:
        custodian = custodians.get(facility.custodian_id) if facility.custodian_id else None
        reads.append(
            FacilityRead(
                id=facility.id,
                name=facility.name,
                description=facility.description,
                department_id=facility.department_id,
                department_name=(
                    department_names.get(facility.department_id) if facility.department_id else None
                ),
                location=facility.location,
                contact=facility.contact,
                custodian_id=facility.custodian_id,
                custodian_name=custodian.full_name if custodian else None,
                custodian_registration_number=(
                    custodian.registration_number if custodian else None
                ),
                equipment_count=counts.get(facility.id, 0),
                created_at=facility.created_at,
            )
        )
    return reads


def list_facilities(
    db: Session,
    params: PageParams,
    *,
    q: str | None = None,
    department_id: uuid.UUID | None = None,
) -> Page[FacilityRead]:
    query = select(Facility)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(
                Facility.name.ilike(pattern),
                Facility.description.ilike(pattern),
                Facility.location.ilike(pattern),
            )
        )
    if department_id is not None:
        query = query.where(Facility.department_id == department_id)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = (
        db.execute(query.order_by(Facility.name).offset(params.offset).limit(params.page_size))
        .scalars()
        .all()
    )
    return Page[FacilityRead](
        items=_facility_reads(db, list(rows)),
        page=params.page,
        page_size=params.page_size,
        total=total,
    )


def get_facility(db: Session, facility_id: uuid.UUID) -> FacilityRead:
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise FacilityNotFoundError
    return _facility_reads(db, [facility])[0]


def create_facility(db: Session, actor: User, data: FacilityCreate) -> FacilityRead:
    department_id = data.department_id
    if actor.role is not UserRole.ADMIN:
        # A coordinator can only create inside their own department, so the
        # scope decides -- an explicit mismatch is rejected rather than moved.
        scope = coordinator_department(actor)
        if scope is None:
            raise DepartmentRequiredError
        if department_id is not None and department_id != scope:
            raise DepartmentRequiredError
        department_id = scope
    facility = Facility(
        name=data.name,
        description=data.description,
        department_id=department_id,
        location=data.location,
        contact=data.contact,
    )
    db.add(facility)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateFacilityError from exc
    db.refresh(facility)
    return _facility_reads(db, [facility])[0]


def _load_managed_facility(db: Session, actor: User, facility_id: uuid.UUID) -> Facility:
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise FacilityNotFoundError
    # Object-level: a custodian's scope is a set of facilities, so the check
    # has to be against this row rather than against a department.
    assert_may_manage_facility(actor, facility)
    return facility


def _facility_of(db: Session, equipment: Equipment) -> Facility:
    """The facility a piece of equipment belongs to.

    Equipment inherits its facility's custodian: whoever looks after the room
    looks after what is in it.
    """
    facility = db.get(Facility, equipment.facility_id)
    if facility is None:  # pragma: no cover - a FK makes this unreachable
        raise FacilityNotFoundError
    return facility


def update_facility(
    db: Session, actor: User, facility_id: uuid.UUID, data: FacilityUpdate
) -> FacilityRead:
    facility = _load_managed_facility(db, actor, facility_id)
    if data.name is not None:
        facility.name = data.name
    for field in ("description", "location", "contact"):
        if field in data.model_fields_set:
            setattr(facility, field, getattr(data, field))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateFacilityError from exc
    db.refresh(facility)
    return _facility_reads(db, [facility])[0]


def delete_facility(db: Session, actor: User, facility_id: uuid.UUID) -> None:
    facility = _load_managed_facility(db, actor, facility_id)
    db.delete(facility)
    db.commit()


def custodian_candidates(
    db: Session, actor: User, facility_id: uuid.UUID
) -> list[CustodianCandidate]:
    """The custodians eligible to look after this facility.

    Same gate as the assignment itself, so being able to see the list and
    being able to use it are one decision. Filtered by the same rules
    `assign_custodian` enforces -- active, holding the role, and in the
    department that runs the facility -- so the picker cannot offer somebody
    the assignment would then refuse.
    """
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise FacilityNotFoundError
    assert_can_manage(actor, facility.department_id)

    query = select(User).where(
        User.role == UserRole.FACILITY_CUSTODIAN,
        User.is_active.is_(True),
    )
    if facility.department_id is not None:
        query = query.where(User.department_id == facility.department_id)
    return [
        CustodianCandidate(
            id=person.id,
            full_name=person.full_name,
            registration_number=person.registration_number,
        )
        for person in db.execute(query.order_by(User.full_name)).scalars()
    ]


def assign_custodian(
    db: Session,
    actor: User,
    facility_id: uuid.UUID,
    data: CustodianAssign,
    *,
    ip: str | None = None,
) -> FacilityRead:
    """Put a facility in somebody's care, or take it out of theirs.

    Gated at DEPARTMENT level (`assert_can_manage`), deliberately not at the
    object level the rest of this module uses. A custodian passes the object
    check for their own facility, so reusing it here would let them hand the
    room to somebody else or seize a colleague's -- the one thing the role
    must not be able to do. Only an admin, or the coordinator of the
    department that runs the facility, may decide who holds it.

    Audited either way: this is a change of authority, not of a label.
    """
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise FacilityNotFoundError
    assert_can_manage(actor, facility.department_id)

    custodian: User | None = None
    if data.user_id is not None:
        custodian = db.get(User, data.user_id)
        # 404 rather than 422: an actor who may manage this facility still has
        # no business learning which account ids exist.
        if custodian is None or not custodian.is_active:
            raise FacilityNotFoundError
        if custodian.role is not UserRole.FACILITY_CUSTODIAN:
            raise NotACustodianError
        if facility.department_id is not None and custodian.department_id != facility.department_id:
            raise CustodianDepartmentError

    before = facility.custodian_id
    if before == data.user_id:
        # Nothing changed; don't write an audit row claiming otherwise.
        return _facility_reads(db, [facility])[0]

    facility.custodian_id = data.user_id
    audit_service.record(
        db,
        actor_id=actor.id,
        action="facility.custodian_assigned" if data.user_id else "facility.custodian_cleared",
        entity_type="facility",
        entity_id=facility.id,
        before={"custodian_id": str(before) if before else None},
        after={"custodian_id": str(data.user_id) if data.user_id else None},
        ip=ip,
    )
    db.commit()
    db.refresh(facility)
    return _facility_reads(db, [facility])[0]


# --- equipment ---------------------------------------------------------------


def _equipment_reads(db: Session, rows: Sequence[Equipment]) -> list[EquipmentRead]:
    if not rows:
        return []
    facilities = {
        facility.id: facility
        for facility in db.execute(
            select(Facility).where(Facility.id.in_({row.facility_id for row in rows}))
        ).scalars()
    }
    return [
        EquipmentRead(
            id=item.id,
            facility_id=item.facility_id,
            facility_name=facilities[item.facility_id].name,
            department_id=facilities[item.facility_id].department_id,
            name=item.name,
            description=item.description,
            category=item.category,
            maintenance_status=item.maintenance_status,
            students_allowed=item.students_allowed,
            requires_approval=item.requires_approval,
            max_hours=item.max_hours,
            min_lead_hours=item.min_lead_hours,
            created_at=item.created_at,
        )
        for item in rows
    ]


def list_equipment(
    db: Session,
    params: PageParams,
    *,
    facility_id: uuid.UUID | None = None,
    category: str | None = None,
    q: str | None = None,
) -> Page[EquipmentRead]:
    query = select(Equipment)
    if facility_id is not None:
        query = query.where(Equipment.facility_id == facility_id)
    if category:
        query = query.where(Equipment.category == category)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(Equipment.name.ilike(pattern), Equipment.description.ilike(pattern))
        )
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = (
        db.execute(query.order_by(Equipment.name).offset(params.offset).limit(params.page_size))
        .scalars()
        .all()
    )
    return Page[EquipmentRead](
        items=_equipment_reads(db, list(rows)),
        page=params.page,
        page_size=params.page_size,
        total=total,
    )


def get_equipment(db: Session, equipment_id: uuid.UUID) -> EquipmentRead:
    return _equipment_reads(db, [load_equipment(db, equipment_id)])[0]


def load_equipment(db: Session, equipment_id: uuid.UUID) -> Equipment:
    equipment = db.get(Equipment, equipment_id)
    if equipment is None:
        raise EquipmentNotFoundError
    return equipment


def equipment_department(db: Session, equipment: Equipment) -> uuid.UUID | None:
    facility = db.get(Facility, equipment.facility_id)
    return facility.department_id if facility else None


def create_equipment(db: Session, actor: User, data: EquipmentCreate) -> EquipmentRead:
    facility = _load_managed_facility(db, actor, data.facility_id)
    equipment = Equipment(
        facility_id=facility.id,
        name=data.name,
        description=data.description,
        category=data.category,
        maintenance_status=data.maintenance_status,
        students_allowed=data.students_allowed,
        requires_approval=data.requires_approval,
        max_hours=data.max_hours,
        min_lead_hours=data.min_lead_hours,
    )
    db.add(equipment)
    db.commit()
    db.refresh(equipment)
    return _equipment_reads(db, [equipment])[0]


def update_equipment(
    db: Session, actor: User, equipment_id: uuid.UUID, data: EquipmentUpdate
) -> EquipmentRead:
    equipment = load_equipment(db, equipment_id)
    assert_may_manage_facility(actor, _facility_of(db, equipment))
    for field in (
        "name",
        "category",
        "maintenance_status",
        "students_allowed",
        "requires_approval",
        "max_hours",
        "min_lead_hours",
    ):
        value = getattr(data, field)
        if value is not None:
            setattr(equipment, field, value)
    if "description" in data.model_fields_set:
        equipment.description = data.description
    db.commit()
    db.refresh(equipment)
    return _equipment_reads(db, [equipment])[0]


def delete_equipment(db: Session, actor: User, equipment_id: uuid.UUID) -> None:
    equipment = load_equipment(db, equipment_id)
    assert_may_manage_facility(actor, _facility_of(db, equipment))
    db.delete(equipment)
    db.commit()
