"""The institutional research report, for one full academic year.

Every figure here comes from a query against real rows. Nothing is estimated,
extrapolated or carried over from a previous run, and each table states the
definition it was produced under -- a number in a report somebody signs has to
be defensible to the person who asks where it came from.

The report is a plain data structure rather than a rendered document, so the
same aggregation feeds the JSON response, the CSV and the PDF. One set of
numbers, three renderings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.analytics import insights
from app.modules.analytics.academic_year import AcademicYear
from app.modules.analytics.insights import Scope
from app.modules.milestones.models import Milestone
from app.modules.profiles.models import ResearcherProfile, VerificationStatus
from app.modules.projects.models import Project, ProjectStatus
from app.modules.publications.models import Publication, PublicationAuthor
from app.modules.users.models import User, UserRole


@dataclass(frozen=True, slots=True)
class ReportTable:
    title: str
    columns: tuple[str, ...]
    rows: list[tuple[str, ...]]
    #: How this table's numbers are defined. Rendered with the table, not
    #: buried in documentation nobody opens next to the figure.
    definition: str | None = None


@dataclass(frozen=True, slots=True)
class ReportSection:
    title: str
    summary: list[tuple[str, str]] = field(default_factory=list)
    tables: list[ReportTable] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class InstitutionalReport:
    academic_year: str
    period_start: str
    period_end: str
    generated_at: str
    scope: str
    sections: list[ReportSection]

    @property
    def filename_stem(self) -> str:
        return f"institutional-research-report-{self.academic_year}"


def _percent(value: float | None) -> str:
    return "not applicable" if value is None else f"{value * 100:.1f}%"


def _labelled(rows: list[insights.LabelledCountRow]) -> list[tuple[str, ...]]:
    return [(row["label"], str(row["count"])) for row in rows]


def build(db: Session, scope: Scope, year: AcademicYear) -> InstitutionalReport:
    """Assemble the whole report for one academic year."""
    start, end = year.start, year.end
    sections: list[ReportSection] = []

    # --- people ------------------------------------------------------------
    # db.scalar on a COUNT returns int, but its signature admits None; the
    # `or 0` below is what the type checker needs and costs nothing.
    researchers = db.scalar(
        select(func.count())
        .select_from(ResearcherProfile)
        .join(User, User.id == ResearcherProfile.user_id)
        .where(User.id.in_(insights._scoped_users(scope)))
    )
    verified = db.scalar(
        select(func.count())
        .select_from(ResearcherProfile)
        .join(User, User.id == ResearcherProfile.user_id)
        .where(
            ResearcherProfile.verification_status == VerificationStatus.VERIFIED,
            User.id.in_(insights._scoped_users(scope)),
        )
    )
    students = db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.role == UserRole.STUDENT, User.id.in_(insights._scoped_users(scope)))
    )
    sections.append(
        ReportSection(
            title="People",
            summary=[
                ("Researcher profiles", str(researchers or 0)),
                ("Verified researchers", str(verified or 0)),
                (
                    "Proportion verified",
                    _percent(((verified or 0) / researchers) if researchers else None),
                ),
                ("Research students", str(students or 0)),
            ],
        )
    )

    # --- projects ----------------------------------------------------------
    by_status = insights.projects_by_status(db, scope)
    completed_in_year = db.scalar(
        select(func.count())
        .select_from(Project)
        .where(
            Project.deleted_at.is_(None),
            Project.status == ProjectStatus.COMPLETED,
            Project.updated_at >= start,
            Project.updated_at <= end,
            Project.id.in_(insights._scoped_projects(scope)),
        )
    )
    adherence = insights.milestone_adherence(db, scope)
    milestones_in_year = db.scalar(
        select(func.count())
        .select_from(Milestone)
        .join(Project, Project.id == Milestone.project_id)
        .where(
            Project.deleted_at.is_(None),
            Milestone.due_date >= start,
            Milestone.due_date <= end,
            Project.id.in_(insights._scoped_projects(scope)),
        )
    )
    sections.append(
        ReportSection(
            title="Research projects",
            summary=[
                ("Projects, all statuses", str(sum(by_status.values()))),
                ("Completed during the year", str(completed_in_year or 0)),
                ("Milestones falling due in the year", str(milestones_in_year or 0)),
                (
                    "Milestones completed on time",
                    _percent(
                        (adherence["completed_on_time"] / adherence["completed"])
                        if adherence["completed"]
                        else None
                    ),
                ),
            ],
            tables=[
                ReportTable(
                    title="Projects by status",
                    columns=("Status", "Projects"),
                    rows=[
                        (status.replace("_", " ").title(), str(count))
                        for status, count in sorted(by_status.items())
                    ],
                    definition="Every project in scope, counted once by its current status.",
                ),
                ReportTable(
                    title="Outstanding milestones by risk",
                    columns=("Risk", "Milestones"),
                    rows=[
                        ("On track", str(adherence["on_track"])),
                        ("Due soon", str(adherence["at_risk"])),
                        ("Blocked", str(adherence["blocked"])),
                        ("Overdue", str(adherence["overdue"])),
                    ],
                    definition=(
                        "Risk is derived at the moment this report ran, from the "
                        "milestone's status, its due date and what it waits on. It "
                        "describes today, not the year."
                    ),
                ),
            ],
        )
    )

    # --- publications ------------------------------------------------------
    total_publications = db.scalar(
        select(func.count())
        .select_from(Publication)
        .where(*insights._publication_window(scope, start, end))
    )
    attributed = db.scalar(
        select(func.count(func.distinct(Publication.id)))
        .select_from(Publication)
        .join(PublicationAuthor, PublicationAuthor.publication_id == Publication.id)
        .join(User, User.id == PublicationAuthor.user_id)
        .where(User.department_id.is_not(None), *insights._publication_window(scope, start, end))
    )
    sections.append(
        ReportSection(
            title="Publications",
            summary=[
                ("Publications in the year", str(total_publications or 0)),
                ("Attributable to a department", str(attributed or 0)),
                (
                    "Not attributable",
                    str((total_publications or 0) - (attributed or 0)),
                ),
            ],
            tables=[
                ReportTable(
                    title="Publications by department",
                    columns=("Department", "Publications"),
                    rows=_labelled(
                        insights.publications_by_department(db, scope, start=start, end=end)
                    ),
                    definition=(
                        "A publication is credited to every department among its "
                        "linked authors, so these figures sum to more than the "
                        "total. Authors recorded only as text have no department "
                        "and are not counted."
                    ),
                ),
                ReportTable(
                    title="Publications by year",
                    columns=("Year", "Publications"),
                    rows=_labelled(insights.publications_by_year(db, scope, start=start, end=end)),
                    definition=(
                        "The publication year on the record. An academic year "
                        "spans two calendar years, so both appear."
                    ),
                ),
                ReportTable(
                    title="Publications by type",
                    columns=("Type", "Publications"),
                    rows=_labelled(insights.publications_by_type(db, scope, start=start, end=end)),
                ),
                ReportTable(
                    title="Busiest venues",
                    columns=("Venue", "Publications"),
                    rows=_labelled(insights.publications_by_venue(db, scope, start=start, end=end)),
                    definition="Top 20. Records with no venue are omitted rather than invented.",
                ),
            ],
        )
    )

    # --- collaboration -----------------------------------------------------
    collaboration = insights.cross_department_collaboration(db, scope)
    sections.append(
        ReportSection(
            title="Collaboration",
            summary=[
                ("Cross-department collaborations", str(collaboration["cross_department"])),
                ("Within one department", str(collaboration["same_department"])),
                ("Cross-department rate", _percent(collaboration["rate"])),
                (
                    "Excluded, department unknown",
                    str(collaboration["unknown_department"]),
                ),
            ],
            tables=[
                ReportTable(
                    title="Cross-department collaboration rate",
                    columns=("Measure", "Value"),
                    rows=[
                        ("Cross-department", str(collaboration["cross_department"])),
                        ("Same department", str(collaboration["same_department"])),
                        ("Rate", _percent(collaboration["rate"])),
                    ],
                    definition=(
                        "rate = cross-department / (cross-department + same "
                        "department). Pairs where either person has no department "
                        "cannot answer the question and are excluded from both "
                        "halves rather than counted as same-department."
                    ),
                )
            ],
        )
    )

    # --- opportunities -----------------------------------------------------
    outcomes = insights.application_success_rate(db, scope, start=start, end=end)
    funnel = insights.opportunity_funnel(db, scope)
    sections.append(
        ReportSection(
            title="Research opportunities",
            summary=[
                ("Applications in the year", str(outcomes["total"])),
                ("Decided", str(outcomes["decided"])),
                ("Still pending", str(outcomes["pending"])),
                ("Success rate", _percent(outcomes["rate"])),
            ],
            tables=[
                ReportTable(
                    title="Application outcomes",
                    columns=("Outcome", "Applications"),
                    rows=[
                        ("Accepted", str(outcomes["accepted"])),
                        ("Rejected", str(outcomes["rejected"])),
                        ("Pending", str(outcomes["pending"])),
                        ("Withdrawn", str(outcomes["withdrawn"])),
                    ],
                    definition=(
                        "success rate = accepted / (accepted + rejected). Pending "
                        "applications have no outcome yet and are not in the "
                        "denominator; withdrawn ones were stopped by the applicant "
                        "and are in neither half."
                    ),
                ),
                ReportTable(
                    title="Opportunity funnel",
                    columns=("Stage", "Count"),
                    rows=[(k.replace("_", " ").title(), str(v)) for k, v in funnel.items()],
                ),
            ],
        )
    )

    # --- facilities --------------------------------------------------------
    utilisation = insights.equipment_utilisation(db, scope)
    sections.append(
        ReportSection(
            title="Facilities and equipment",
            summary=[("Equipment with recorded bookings", str(len(utilisation)))],
            tables=[
                ReportTable(
                    title="Equipment utilisation",
                    columns=("Equipment", "Approved bookings", "Hours booked"),
                    rows=[
                        (row["label"], str(row["bookings"]), f"{row['hours']:.1f}")
                        for row in utilisation
                    ],
                    definition=(
                        "Approved bookings only. Pending and rejected requests are excluded."
                    ),
                )
            ],
        )
    )

    # --- funding -----------------------------------------------------------
    funding = insights.funding_interest(db, scope)
    sections.append(
        ReportSection(
            title="Funding",
            summary=[("Funding calls attracting interest", str(len(funding)))],
            tables=[
                ReportTable(
                    title="Funding calls by recorded interest",
                    columns=("Funding call", "People interested"),
                    rows=_labelled(funding),
                    definition=(
                        "Counted from saved items, which is the only interest "
                        "this platform records."
                    ),
                )
            ],
        )
    )

    return InstitutionalReport(
        academic_year=year.label,
        period_start=year.start.isoformat(),
        period_end=year.end.isoformat(),
        generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        scope="the whole institution" if scope.is_platform else "one department",
        sections=sections,
    )


__all__ = ["InstitutionalReport", "ReportSection", "ReportTable", "build"]
