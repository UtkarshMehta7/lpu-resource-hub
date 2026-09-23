"""Aggregate analytics.

Two rules shape everything here:

* **Scope**: a coordinator sees their own department, an admin sees the
  platform. The scope is applied inside each query, so a coordinator can't
  widen it with a parameter.
* **No raw personal data**: these endpoints return counts, not people. The
  one exception is the verification backlog's oldest-waiting timestamp, which
  is a date, not a name.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict

from sqlalchemy import ColumnElement, Row, Select, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.modules.applications.models import Application, ApplicationStatus
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.collaborations.models import CollaborationRequest, CollaborationStatus
from app.modules.facilities.models import Equipment, Facility
from app.modules.funding.models import FundingOpportunity
from app.modules.opportunities.models import Opportunity, OpportunityStatus
from app.modules.profiles.models import ResearcherProfile, SavedItem, VerificationStatus
from app.modules.projects.models import Project, ProjectResearchArea, ProjectStatus
from app.modules.reports.models import ContentReport, ReportStatus
from app.modules.taxonomy.models import ResearchArea
from app.modules.users.models import CoordinatorScopeType, User, UserRole


class LabelledCountRow(TypedDict):
    label: str
    count: int


class EquipmentUsageRow(TypedDict):
    label: str
    hours: float
    bookings: int


class TrendRow(TypedDict):
    month: str
    projects: int
    applications: int
    bookings: int


class BacklogRow(TypedDict):
    pending: int
    oldest_waiting_since: str | None


TREND_MONTHS = 6
TOP_N = 8


@dataclass(frozen=True, slots=True)
class Scope:
    """Which slice of the platform a viewer may see."""

    department_id: uuid.UUID | None  # None = the whole platform (admin)

    @property
    def is_platform(self) -> bool:
        return self.department_id is None


def scope_for(user: User) -> Scope:
    if user.role is UserRole.ADMIN:
        return Scope(department_id=None)
    if (
        user.role is UserRole.RESEARCH_COORDINATOR
        and user.coordinator_scope_type is CoordinatorScopeType.DEPARTMENT
    ):
        return Scope(department_id=user.coordinator_scope_id)
    # A coordinator with no department scope oversees nothing.
    return Scope(department_id=uuid.UUID(int=0))


def _scoped_projects(scope: Scope) -> Select[tuple[uuid.UUID]]:
    query = select(Project.id).where(Project.deleted_at.is_(None))
    if not scope.is_platform:
        query = query.where(Project.department_id == scope.department_id)
    return query


def _scoped_opportunities(scope: Scope) -> Select[tuple[uuid.UUID]]:
    query = select(Opportunity.id)
    if not scope.is_platform:
        query = query.where(Opportunity.department_id == scope.department_id)
    return query


def _scoped_equipment(scope: Scope) -> Select[tuple[uuid.UUID]]:
    query = select(Equipment.id).join(Facility, Facility.id == Equipment.facility_id)
    if not scope.is_platform:
        query = query.where(Facility.department_id == scope.department_id)
    return query


def _scoped_users(scope: Scope) -> Select[tuple[uuid.UUID]]:
    query = select(User.id).where(User.is_active.is_(True))
    if not scope.is_platform:
        query = query.where(User.department_id == scope.department_id)
    return query


def _counts(rows: Sequence[Row[tuple[Any, int]]]) -> dict[str, int]:
    """Enum-keyed group-by rows as plain string counts."""
    return {str(getattr(key, "value", key)): int(value) for key, value in rows}


def projects_by_status(db: Session, scope: Scope) -> dict[str, int]:
    base = {status.value: 0 for status in ProjectStatus}
    rows = db.execute(
        select(Project.status, func.count())
        .where(Project.id.in_(_scoped_projects(scope)))
        .group_by(Project.status)
    ).all()
    return base | _counts(rows)


def projects_by_area(db: Session, scope: Scope) -> list[LabelledCountRow]:
    rows = db.execute(
        select(ResearchArea.name, func.count())
        .join(ProjectResearchArea, ProjectResearchArea.research_area_id == ResearchArea.id)
        .where(ProjectResearchArea.project_id.in_(_scoped_projects(scope)))
        .group_by(ResearchArea.name)
        .order_by(func.count().desc(), ResearchArea.name)
        .limit(TOP_N)
    ).all()
    return [LabelledCountRow(label=name, count=int(count)) for name, count in rows]


def opportunity_funnel(db: Session, scope: Scope) -> dict[str, int]:
    opportunities = _scoped_opportunities(scope)
    by_status = {status.value: 0 for status in OpportunityStatus} | _counts(
        db.execute(
            select(Opportunity.status, func.count())
            .where(Opportunity.id.in_(opportunities))
            .group_by(Opportunity.status)
        ).all(),
    )
    applications = {status.value: 0 for status in ApplicationStatus} | _counts(
        db.execute(
            select(Application.status, func.count())
            .where(Application.opportunity_id.in_(opportunities))
            .group_by(Application.status)
        ).all(),
    )
    return {
        **{f"opportunities_{key}": value for key, value in by_status.items()},
        **{f"applications_{key}": value for key, value in applications.items()},
    }


def equipment_utilisation(db: Session, scope: Scope) -> list[EquipmentUsageRow]:
    """Approved booked hours per item, most used first."""
    hours = func.sum(
        func.extract("epoch", func.upper(Booking.period) - func.lower(Booking.period)) / 3600.0
    )
    rows = db.execute(
        select(Equipment.name, hours, func.count())
        .join(Booking, Booking.equipment_id == Equipment.id)
        .where(
            Equipment.id.in_(_scoped_equipment(scope)),
            Booking.status == BookingStatus.APPROVED,
        )
        .group_by(Equipment.name)
        .order_by(hours.desc())
        .limit(TOP_N)
    ).all()
    return [
        EquipmentUsageRow(label=name, hours=round(float(total or 0), 1), bookings=int(count))
        for name, total, count in rows
    ]


def funding_interest(db: Session, scope: Scope) -> list[LabelledCountRow]:
    """Which funding calls people saved. Funding is university-wide, so a
    coordinator sees saves by people in their department."""
    savers = select(SavedItem.funding_id).where(SavedItem.funding_id.is_not(None))
    if not scope.is_platform:
        savers = savers.where(SavedItem.user_id.in_(_scoped_users(scope)))
    rows = db.execute(
        select(FundingOpportunity.title, func.count())
        .join(SavedItem, SavedItem.funding_id == FundingOpportunity.id)
        .where(FundingOpportunity.id.in_(savers))
        .group_by(FundingOpportunity.title)
        .order_by(func.count().desc(), FundingOpportunity.title)
        .limit(TOP_N)
    ).all()
    return [LabelledCountRow(label=title, count=int(count)) for title, count in rows]


def verification_backlog(db: Session, scope: Scope) -> BacklogRow:
    query = select(func.count(), func.min(ResearcherProfile.updated_at)).where(
        ResearcherProfile.verification_status == VerificationStatus.PENDING
    )
    if not scope.is_platform:
        query = query.where(ResearcherProfile.user_id.in_(_scoped_users(scope)))
    pending, oldest = db.execute(query).one()
    return BacklogRow(
        pending=int(pending or 0),
        # A timestamp, not a person: enough to see a queue going stale.
        oldest_waiting_since=oldest.isoformat() if oldest else None,
    )


def open_reports(db: Session) -> int:
    return int(
        db.execute(
            select(func.count()).where(ContentReport.status == ReportStatus.OPEN)
        ).scalar_one()
    )


def _monthly(
    db: Session,
    created_at: InstrumentedAttribute[datetime],
    restriction: ColumnElement[bool],
) -> dict[str, int]:
    since = datetime.now(UTC) - timedelta(days=30 * TREND_MONTHS)
    month = func.to_char(created_at, "YYYY-MM")
    rows = db.execute(
        select(month, func.count()).where(created_at >= since, restriction).group_by(month)
    ).all()
    return {str(label): int(count) for label, count in rows}


def trends(db: Session, scope: Scope) -> list[TrendRow]:
    """Counts per month for the last six months, oldest first."""
    projects = _monthly(db, Project.created_at, Project.id.in_(_scoped_projects(scope)))
    applications = _monthly(
        db, Application.created_at, Application.opportunity_id.in_(_scoped_opportunities(scope))
    )
    bookings = _monthly(db, Booking.created_at, Booking.equipment_id.in_(_scoped_equipment(scope)))

    months: list[str] = []
    cursor = datetime.now(UTC).replace(day=1)
    for _ in range(TREND_MONTHS):
        months.append(cursor.strftime("%Y-%m"))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    months.reverse()
    return [
        TrendRow(
            month=month,
            projects=projects.get(month, 0),
            applications=applications.get(month, 0),
            bookings=bookings.get(month, 0),
        )
        for month in months
    ]


def collaboration_totals(db: Session, scope: Scope) -> dict[str, int]:
    query = select(func.count()).where(CollaborationRequest.status == CollaborationStatus.ACCEPTED)
    if not scope.is_platform:
        people = _scoped_users(scope)
        query = query.where(
            or_(
                CollaborationRequest.sender_id.in_(people),
                CollaborationRequest.recipient_id.in_(people),
            )
        )
    return {"accepted_collaborations": int(db.execute(query).scalar_one())}
