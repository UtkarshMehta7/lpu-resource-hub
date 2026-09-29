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
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypedDict

from sqlalchemy import ColumnElement, Row, Select, func, or_, select, true
from sqlalchemy.orm import InstrumentedAttribute, Session, aliased

from app.modules.admin.models import Department
from app.modules.applications.models import Application, ApplicationStatus
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.collaborations.models import (
    Collaboration,
    CollaborationRequest,
    CollaborationStatus,
)
from app.modules.facilities.models import Equipment, Facility
from app.modules.funding.models import FundingOpportunity
from app.modules.milestones.models import (
    SETTLED_STATUSES,
    Milestone,
    MilestoneDependency,
)
from app.modules.milestones.risk import Risk, RiskInput, assess
from app.modules.opportunities.models import Opportunity, OpportunityStatus
from app.modules.profiles.models import ResearcherProfile, SavedItem, VerificationStatus
from app.modules.projects.models import Project, ProjectResearchArea, ProjectStatus
from app.modules.publications.models import Publication, PublicationAuthor
from app.modules.reports.models import ContentReport, ReportStatus
from app.modules.taxonomy.models import ResearchArea
from app.modules.users.models import CoordinatorScopeType, User, UserRole


class LabelledCountRow(TypedDict):
    label: str
    count: int


class CollaborationRateRow(TypedDict):
    """Collaboration split by whether it crossed a departmental boundary."""

    cross_department: int
    same_department: int
    #: Pairs where at least one person has no department, so the question
    #: cannot be answered for them. Excluded from the rate, never hidden.
    unknown_department: int
    #: None when nothing qualifies -- no collaborations is not a zero rate.
    rate: float | None


class ApplicationOutcomeRow(TypedDict):
    total: int
    accepted: int
    rejected: int
    pending: int
    withdrawn: int
    decided: int
    rate: float | None


class MilestoneAdherenceRow(TypedDict):
    """How the outstanding milestones in scope are doing, plus what's landed."""

    on_track: int
    at_risk: int
    overdue: int
    blocked: int
    completed: int
    completed_on_time: int


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


def milestone_adherence(db: Session, scope: Scope) -> MilestoneAdherenceRow:
    """Counts per risk state, plus how much of what finished finished on time.

    Risk is derived the same way the API derives it, by calling the same
    function -- an analytics view that computed "at risk" its own way would
    eventually disagree with the project page, and the number people trust is
    whichever one they saw last.
    """
    from app.core.config import get_settings

    today = datetime.now(UTC).date()
    threshold = get_settings().milestone_at_risk_days

    rows = db.execute(
        select(Milestone.id, Milestone.status, Milestone.due_date, Milestone.completed_at)
        .join(Project, Project.id == Milestone.project_id)
        .where(Project.deleted_at.is_(None), Project.id.in_(_scoped_projects(scope)))
    ).all()

    edges: dict[uuid.UUID, list[uuid.UUID]] = {}
    by_id = {row.id: row for row in rows}
    if by_id:
        for milestone_id, depends_on_id in db.execute(
            select(MilestoneDependency.milestone_id, MilestoneDependency.depends_on_id).where(
                MilestoneDependency.milestone_id.in_(by_id)
            )
        ).all():
            edges.setdefault(milestone_id, []).append(depends_on_id)

    counts: dict[str, int] = {
        "on_track": 0,
        "at_risk": 0,
        "overdue": 0,
        "blocked": 0,
        "completed": 0,
        "completed_on_time": 0,
    }
    for row in rows:
        if row.status in SETTLED_STATUSES:
            if row.completed_at is not None:
                counts["completed"] += 1
                if row.completed_at.date() <= row.due_date:
                    counts["completed_on_time"] += 1
            continue
        risk = assess(
            RiskInput(status=row.status, due_date=row.due_date),
            today=today,
            threshold_days=threshold,
            depends_on=[
                RiskInput(status=by_id[dep].status, due_date=by_id[dep].due_date)
                for dep in edges.get(row.id, [])
                if dep in by_id
            ],
        )
        if risk is Risk.ON_TRACK:
            counts["on_track"] += 1
        elif risk is Risk.AT_RISK:
            counts["at_risk"] += 1
        elif risk is Risk.OVERDUE:
            counts["overdue"] += 1
        elif risk is Risk.BLOCKED:
            counts["blocked"] += 1
    return MilestoneAdherenceRow(
        on_track=counts["on_track"],
        at_risk=counts["at_risk"],
        overdue=counts["overdue"],
        blocked=counts["blocked"],
        completed=counts["completed"],
        completed_on_time=counts["completed_on_time"],
    )


# --- publications ----------------------------------------------------------
#
# A publication belongs to a department through its *linked* authors -- the
# ones matched to an account. External co-authors are plain text and have no
# department, which is why every figure below also reports what it could not
# attribute rather than quietly dropping it.


def _publication_window(
    scope: Scope, start: date | None, end: date | None
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    if start is not None and end is not None:
        # `year` is the publication year, which is the only date a
        # bibliographic record reliably carries.
        filters.append(Publication.year.between(start.year, end.year))
    if not scope.is_platform:
        filters.append(
            Publication.id.in_(
                select(PublicationAuthor.publication_id)
                .join(User, User.id == PublicationAuthor.user_id)
                .where(User.department_id == scope.department_id)
            )
        )
    return filters


def publications_by_department(
    db: Session, scope: Scope, *, start: date | None = None, end: date | None = None
) -> list[LabelledCountRow]:
    """Distinct publications credited to each department.

    A publication with authors in two departments counts once in each, so
    these figures sum to more than the total. That is the intended reading:
    the question is "how much did this department produce", not "how do we
    slice a fixed total".
    """
    rows = db.execute(
        select(Department.name, func.count(func.distinct(Publication.id)))
        .select_from(Publication)
        .join(PublicationAuthor, PublicationAuthor.publication_id == Publication.id)
        .join(User, User.id == PublicationAuthor.user_id)
        .join(Department, Department.id == User.department_id)
        .where(*_publication_window(scope, start, end))
        .group_by(Department.name)
        .order_by(func.count(func.distinct(Publication.id)).desc(), Department.name)
    ).all()
    return [LabelledCountRow(label=row[0], count=row[1]) for row in rows]


def publications_by_year(
    db: Session, scope: Scope, *, start: date | None = None, end: date | None = None
) -> list[LabelledCountRow]:
    rows = db.execute(
        select(Publication.year, func.count())
        .where(*_publication_window(scope, start, end))
        .group_by(Publication.year)
        .order_by(Publication.year.desc())
    ).all()
    return [LabelledCountRow(label=str(row[0]), count=row[1]) for row in rows]


def publications_by_venue(
    db: Session,
    scope: Scope,
    *,
    start: date | None = None,
    end: date | None = None,
    limit: int = 20,
) -> list[LabelledCountRow]:
    """Busiest venues first. Records with no venue are excluded, not bucketed
    as "Unknown" -- a made-up venue name in a report is worse than a shorter
    list, and the total publication count is reported separately anyway."""
    rows = db.execute(
        select(Publication.venue, func.count())
        .where(Publication.venue.is_not(None), *_publication_window(scope, start, end))
        .group_by(Publication.venue)
        .order_by(func.count().desc(), Publication.venue)
        .limit(limit)
    ).all()
    return [LabelledCountRow(label=row[0], count=row[1]) for row in rows]


def publications_by_type(
    db: Session, scope: Scope, *, start: date | None = None, end: date | None = None
) -> list[LabelledCountRow]:
    rows = db.execute(
        select(Publication.pub_type, func.count())
        .where(*_publication_window(scope, start, end))
        .group_by(Publication.pub_type)
        .order_by(func.count().desc())
    ).all()
    return [
        LabelledCountRow(label=row[0].value.replace("_", " ").title(), count=row[1]) for row in rows
    ]


# --- collaboration ---------------------------------------------------------


def cross_department_collaboration(db: Session, scope: Scope) -> CollaborationRateRow:
    """How much collaboration crosses a departmental boundary.

        rate = cross_department / (cross_department + same_department)

    Only pairs where *both* people have a department can answer the question,
    so pairs with one missing are excluded from both halves and counted
    separately as `unknown_department`. Rolling them into the denominator
    would depress the rate for a reason that has nothing to do with
    collaboration.

    Reported as a fraction 0-1; the interface formats it.
    """
    a = aliased(User)
    b = aliased(User)
    rows = db.execute(
        select(a.department_id, b.department_id)
        .select_from(Collaboration)
        .join(a, a.id == Collaboration.user_a_id)
        .join(b, b.id == Collaboration.user_b_id)
        .where(
            true()
            if scope.is_platform
            else or_(
                a.department_id == scope.department_id,
                b.department_id == scope.department_id,
            )
        )
    ).all()

    same = cross = unknown = 0
    for left, right in rows:
        if left is None or right is None:
            unknown += 1
        elif left == right:
            same += 1
        else:
            cross += 1
    qualifying = same + cross
    return CollaborationRateRow(
        cross_department=cross,
        same_department=same,
        unknown_department=unknown,
        # Zero collaborations is not a zero rate, it is no rate at all.
        rate=(cross / qualifying) if qualifying else None,
    )


# --- applications ----------------------------------------------------------


def application_success_rate(
    db: Session, scope: Scope, *, start: date | None = None, end: date | None = None
) -> ApplicationOutcomeRow:
    """Outcomes of applications to research opportunities.

        success rate = accepted / (accepted + rejected)

    Only *decided* applications are in the denominator. Pending ones
    (submitted, under review, shortlisted) have no outcome yet, and counting
    them as failures would make the rate fall simply because a reviewer is
    slow. Withdrawn applications are excluded from both halves: the applicant
    stopped, which is not a decision anyone made about them.

    The specification calls this "funding application success rate". This
    platform's funding module is a register of calls with deadlines and
    saved interest -- it has no application workflow, and neither does the
    specification's own M6 -- so the applications measured here are those to
    research opportunities (M4). Stated plainly rather than relabelled.
    """
    filters: list[ColumnElement[bool]] = []
    if start is not None and end is not None:
        filters.append(Application.created_at >= start)
        filters.append(Application.created_at <= end)
    if not scope.is_platform:
        filters.append(Application.opportunity_id.in_(_scoped_opportunities(scope)))

    counts = _counts(
        db.execute(
            select(Application.status, func.count()).where(*filters).group_by(Application.status)
        ).all()
    )
    accepted = counts.get(ApplicationStatus.ACCEPTED.value, 0)
    rejected = counts.get(ApplicationStatus.REJECTED.value, 0)
    withdrawn = counts.get(ApplicationStatus.WITHDRAWN.value, 0)
    decided = accepted + rejected
    pending = sum(
        count
        for status, count in counts.items()
        if status
        not in (
            ApplicationStatus.ACCEPTED.value,
            ApplicationStatus.REJECTED.value,
            ApplicationStatus.WITHDRAWN.value,
        )
    )
    return ApplicationOutcomeRow(
        total=sum(counts.values()),
        accepted=accepted,
        rejected=rejected,
        pending=pending,
        withdrawn=withdrawn,
        decided=decided,
        rate=(accepted / decided) if decided else None,
    )
