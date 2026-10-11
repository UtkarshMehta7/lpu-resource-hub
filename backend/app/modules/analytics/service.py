"""Dashboard aggregates.

Every count here is scoped the same way the corresponding list endpoint is:
a coordinator's numbers cover their department, a faculty member's cover
their own work. Nothing aggregates across a boundary the caller couldn't
browse item by item.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ml.features import ScoreWeights
from app.modules.admin.models import Department, School
from app.modules.analytics import insights
from app.modules.analytics.schemas import (
    AdminDashboard,
    AnnouncementsPanel,
    CoordinatorDashboard,
    CustodianDashboard,
    DashboardResponse,
    DeadlineItem,
    DeanDashboard,
    FacultyDashboard,
    StudentDashboard,
)
from app.modules.announcements import service as announcements_service
from app.modules.applications.models import Application, ApplicationStatus
from app.modules.audit.models import AuditLog
from app.modules.audit.schemas import AuditLogRead
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.collaborations.models import CollaborationRequest, CollaborationStatus
from app.modules.facilities.models import Equipment, Facility
from app.modules.funding.models import FundingOpportunity, FundingStatus
from app.modules.opportunities.models import Opportunity, OpportunityStatus
from app.modules.opportunities.schemas import OpportunityCard
from app.modules.opportunities.service import opportunity_cards
from app.modules.profiles.models import ResearcherProfile, SavedItem, StudentProfile
from app.modules.projects.models import Project, ProjectMember, ProjectStatus
from app.modules.projects.policies import crosses_departments
from app.modules.projects.schemas import ProjectCard
from app.modules.projects.service import project_cards, review_queue
from app.modules.publications.models import Publication, PublicationAuthor
from app.modules.recommendations.schemas import TargetType
from app.modules.recommendations.service import recommend
from app.modules.reports.models import ContentReport, ReportStatus
from app.modules.researchers.search_schemas import ResearcherCard
from app.modules.researchers.service import list_verification_queue, to_queue_item
from app.modules.users.models import CoordinatorScopeType, User, UserRole

logger = logging.getLogger(__name__)

RECOMMENDATION_PREVIEW = 3
DEADLINE_WINDOW_DAYS = 30
ACTIVITY_WINDOW_DAYS = 30
QUEUE_PREVIEW = 5
AUDIT_PREVIEW = 5

OPEN_APPLICATION_STATUSES = (
    ApplicationStatus.SUBMITTED,
    ApplicationStatus.UNDER_REVIEW,
    ApplicationStatus.SHORTLISTED,
)


def _scalar(db: Session, statement: Select[tuple[int]]) -> int:
    return int(db.execute(statement).scalar_one() or 0)


def _pending_inbox(db: Session, user: User) -> int:
    return _scalar(
        db,
        select(func.count()).where(
            CollaborationRequest.recipient_id == user.id,
            CollaborationRequest.status == CollaborationStatus.PENDING,
        ),
    )


def _student_section(db: Session, user: User, weights: ScoreWeights) -> StudentDashboard:
    by_status = {status.value: 0 for status in ApplicationStatus} | {
        status: count
        for status, count in db.execute(
            select(Application.status, func.count())
            .where(Application.applicant_id == user.id)
            .group_by(Application.status)
        ).all()
    }

    def preview(target: TargetType) -> list[object]:
        """The cards behind the top few recommendations for this viewer."""
        return [
            item.item for item in recommend(db, user, target, RECOMMENDATION_PREVIEW, weights).items
        ]

    return StudentDashboard(
        recommended_opportunities=[
            card for card in preview(TargetType.OPPORTUNITIES) if isinstance(card, OpportunityCard)
        ],
        recommended_projects=[
            card for card in preview(TargetType.PROJECTS) if isinstance(card, ProjectCard)
        ],
        recommended_researchers=[
            card for card in preview(TargetType.RESEARCHERS) if isinstance(card, ResearcherCard)
        ],
        saved_count=_scalar(db, select(func.count()).where(SavedItem.user_id == user.id)),
        applications_by_status={str(key): int(value) for key, value in by_status.items()},
        pending_collaboration_requests=_pending_inbox(db, user),
        upcoming_deadlines=_upcoming_deadlines(db, user),
    )


def _upcoming_deadlines(db: Session, user: User) -> list[DeadlineItem]:
    """Openings and funding calls the viewer applied to or saved, closing within 30 days."""
    today = datetime.now(UTC).date()
    applied = select(Application.opportunity_id).where(
        Application.applicant_id == user.id,
        Application.status.in_(OPEN_APPLICATION_STATUSES),
    )
    saved = select(SavedItem.opportunity_id).where(
        SavedItem.user_id == user.id, SavedItem.opportunity_id.is_not(None)
    )
    rows = db.execute(
        select(Opportunity.id, Opportunity.title, Opportunity.deadline)
        .where(
            Opportunity.status == OpportunityStatus.OPEN,
            Opportunity.deadline >= today,
            Opportunity.deadline <= today + timedelta(days=DEADLINE_WINDOW_DAYS),
            or_(Opportunity.id.in_(applied), Opportunity.id.in_(saved)),
        )
        .order_by(Opportunity.deadline)
    ).all()
    applied_ids = set(db.execute(applied).scalars())
    items = [
        DeadlineItem(
            kind="opportunity",
            item_id=opportunity_id,
            title=title,
            deadline=deadline,
            applied=opportunity_id in applied_ids,
        )
        for opportunity_id, title, deadline in rows
    ]
    funding_rows = db.execute(
        select(FundingOpportunity.id, FundingOpportunity.title, FundingOpportunity.deadline)
        .where(
            FundingOpportunity.status == FundingStatus.OPEN,
            FundingOpportunity.deadline >= today,
            FundingOpportunity.deadline <= today + timedelta(days=DEADLINE_WINDOW_DAYS),
            FundingOpportunity.id.in_(
                select(SavedItem.funding_id).where(
                    SavedItem.user_id == user.id, SavedItem.funding_id.is_not(None)
                )
            ),
        )
        .order_by(FundingOpportunity.deadline)
    ).all()
    items.extend(
        DeadlineItem(
            kind="funding", item_id=funding_id, title=title, deadline=deadline, applied=False
        )
        for funding_id, title, deadline in funding_rows
    )
    items.sort(key=lambda item: item.deadline)
    return items


def _faculty_section(db: Session, user: User) -> FacultyDashboard:
    my_projects = (
        db.execute(
            select(Project)
            .where(Project.owner_id == user.id, Project.deleted_at.is_(None))
            .order_by(Project.updated_at.desc())
            .limit(QUEUE_PREVIEW)
        )
        .scalars()
        .all()
    )
    by_status = {status.value: 0 for status in ProjectStatus} | {
        status: count
        for status, count in db.execute(
            select(Project.status, func.count())
            .where(Project.owner_id == user.id, Project.deleted_at.is_(None))
            .group_by(Project.status)
        ).all()
    }
    open_opportunities = (
        db.execute(
            select(Opportunity)
            .where(
                Opportunity.created_by == user.id,
                Opportunity.status == OpportunityStatus.OPEN,
            )
            .order_by(Opportunity.deadline)
            .limit(QUEUE_PREVIEW)
        )
        .scalars()
        .all()
    )
    my_opportunities = select(Opportunity.id).where(Opportunity.created_by == user.id)
    my_project_ids = select(Project.id).where(
        Project.owner_id == user.id, Project.deleted_at.is_(None)
    )
    return FacultyDashboard(
        my_projects=project_cards(db, list(my_projects)),
        projects_by_status={str(key): int(value) for key, value in by_status.items()},
        open_opportunities=opportunity_cards(db, user, list(open_opportunities)),
        pending_applications=_scalar(
            db,
            select(func.count()).where(
                Application.opportunity_id.in_(my_opportunities),
                Application.status.in_(OPEN_APPLICATION_STATUSES),
            ),
        ),
        team_members=_scalar(
            db,
            select(func.count(func.distinct(ProjectMember.user_id))).where(
                ProjectMember.project_id.in_(my_project_ids)
            ),
        ),
        accepted_collaborations=_scalar(
            db,
            select(func.count()).where(
                CollaborationRequest.status == CollaborationStatus.ACCEPTED,
                or_(
                    CollaborationRequest.sender_id == user.id,
                    CollaborationRequest.recipient_id == user.id,
                ),
            ),
        ),
        publications=_scalar(
            db,
            select(func.count(func.distinct(Publication.id)))
            .select_from(Publication)
            .outerjoin(PublicationAuthor, PublicationAuthor.publication_id == Publication.id)
            .where(
                or_(
                    Publication.created_by == user.id,
                    PublicationAuthor.user_id == user.id,
                )
            ),
        ),
        pending_collaboration_requests=_pending_inbox(db, user),
    )


def _coordinator_section(db: Session, user: User) -> CoordinatorDashboard:
    since = datetime.now(UTC) - timedelta(days=ACTIVITY_WINDOW_DAYS)
    scope = (
        user.coordinator_scope_id
        if user.coordinator_scope_type is CoordinatorScopeType.DEPARTMENT
        else None
    )
    department_projects = select(Project.id).where(
        Project.deleted_at.is_(None),
        Project.department_id == scope if scope is not None else Project.id.is_not(None),
    )
    activity = {
        "new_projects": _scalar(
            db,
            select(func.count()).where(
                Project.created_at >= since, Project.id.in_(department_projects)
            ),
        ),
        "new_opportunities": _scalar(
            db,
            select(func.count()).where(
                Opportunity.created_at >= since,
                Opportunity.department_id == scope
                if scope is not None
                else Opportunity.id.is_not(None),
            ),
        ),
        "new_applications": _scalar(
            db,
            select(func.count())
            .select_from(Application)
            .join(Opportunity, Opportunity.id == Application.opportunity_id)
            .where(
                Application.created_at >= since,
                Opportunity.department_id == scope
                if scope is not None
                else Opportunity.id.is_not(None),
            ),
        ),
    }
    return CoordinatorDashboard(
        pending_verifications=[
            to_queue_item(queued_user, profile)
            for queued_user, profile in list_verification_queue(db, user)[:QUEUE_PREVIEW]
        ],
        pending_reviews=review_queue(db, user)[:QUEUE_PREVIEW],
        open_reports=_scalar(
            db, select(func.count()).where(ContentReport.status == ReportStatus.OPEN)
        ),
        department_activity=activity,
    )


def _admin_section(db: Session) -> AdminDashboard:
    by_role = {role.value: 0 for role in UserRole} | {
        role: count
        for role, count in db.execute(
            select(User.role, func.count()).where(User.is_active.is_(True)).group_by(User.role)
        ).all()
    }
    counts = {
        "schools": _scalar(db, select(func.count()).select_from(School)),
        "departments": _scalar(db, select(func.count()).select_from(Department)),
        "projects": _scalar(db, select(func.count()).where(Project.deleted_at.is_(None))),
        "publications": _scalar(db, select(func.count()).select_from(Publication)),
        "opportunities": _scalar(db, select(func.count()).select_from(Opportunity)),
        "applications": _scalar(db, select(func.count()).select_from(Application)),
        "collaborations": _scalar(db, select(func.count()).select_from(CollaborationRequest)),
        "researcher_profiles": _scalar(db, select(func.count()).select_from(ResearcherProfile)),
        "student_profiles": _scalar(db, select(func.count()).select_from(StudentProfile)),
    }
    recent = (
        db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(AUDIT_PREVIEW))
        .scalars()
        .all()
    )
    return AdminDashboard(
        users_by_role={str(key): int(value) for key, value in by_role.items()},
        platform_counts=counts,
        open_reports=_scalar(
            db, select(func.count()).where(ContentReport.status == ReportStatus.OPEN)
        ),
        recent_audit=[AuditLogRead.model_validate(entry) for entry in recent],
    )


def _dean_section(db: Session, user: User) -> DeanDashboard:
    """Institution-wide figures, each one something the dean can act on.

    Built from the same helpers the analytics page uses rather than counted
    again here, so the dashboard and the page cannot disagree about the same
    number -- which is the kind of discrepancy nobody reports and everybody
    stops trusting.
    """
    rows = insights.by_department(db)
    platform = insights.Scope(department_id=None)
    adherence = insights.milestone_adherence(db, platform)
    backlog = insights.verification_backlog(db, platform)
    statuses = insights.projects_by_status(db, platform)

    pending = [
        project
        for project in db.execute(
            select(Project).where(
                Project.deleted_at.is_(None), Project.status == ProjectStatus.PENDING_REVIEW
            )
        )
        .scalars()
        .all()
        if crosses_departments(db, project)
    ]

    return DeanDashboard(
        departments=len(rows),
        departments_needing_attention=sum(
            1 for row in rows if row.milestones_overdue or row.milestones_at_risk
        ),
        projects_at_risk=int(adherence.get("overdue", 0)) + int(adherence.get("at_risk", 0)),
        pending_cross_department_reviews=len(pending),
        verification_backlog=int(backlog.get("pending", 0)),
        active_projects=int(statuses.get("active", 0)),
        researchers=sum(row.researchers for row in rows),
    )


def _custodian_section(db: Session, user: User) -> CustodianDashboard:
    """The rooms this person holds, and what is waiting on them."""
    facility_ids = list(
        db.execute(select(Facility.id).where(Facility.custodian_id == user.id)).scalars().all()
    )
    if not facility_ids:
        return CustodianDashboard(facilities_held=0, equipment=0, bookings_awaiting_decision=0)
    equipment_ids = list(
        db.execute(select(Equipment.id).where(Equipment.facility_id.in_(facility_ids)))
        .scalars()
        .all()
    )
    waiting = (
        _scalar(
            db,
            select(func.count())
            .select_from(Booking)
            .where(
                Booking.equipment_id.in_(equipment_ids),
                Booking.status == BookingStatus.PENDING,
            ),
        )
        if equipment_ids
        else 0
    )
    return CustodianDashboard(
        facilities_held=len(facility_ids),
        equipment=len(equipment_ids),
        bookings_awaiting_decision=waiting,
    )


def _announcements_panel(db: Session, user: User) -> AnnouncementsPanel:
    """The board, for every role, and never at the dashboard's expense.

    Runs in a SAVEPOINT and swallows SQLAlchemyError, like the chat threads
    opened on acceptance. The dashboard is the older and more important act:
    every role signs in to it, and this is a new dependency from that old
    code to a new table. Shipping the code before its migration reached a
    database would otherwise make every dashboard answer 500 for everybody --
    an additive feature taking down an existing one, which is exactly the
    failure AGENTS.md records against the acceptance path.

    An empty panel is the degraded state, and it reads as "nothing announced
    lately" rather than as an error, which is the right thing for a reader
    who cannot act on the difference.
    """
    try:
        with db.begin_nested():
            latest, unread = announcements_service.recent_for_dashboard(db, user)
    except SQLAlchemyError:
        logger.warning("dashboard: the announcements panel could not be built", exc_info=True)
        return AnnouncementsPanel(unread=0, latest=[])
    return AnnouncementsPanel(unread=unread, latest=latest)


def dashboard(db: Session, user: User, weights: ScoreWeights) -> DashboardResponse:
    response = DashboardResponse(role=user.role, onboarding_complete=user.onboarding_complete)
    # Outside the per-role dispatch below, deliberately: a notice is the one
    # thing addressed to everybody, so the panel is not something a role
    # either has or lacks (ADR 0038).
    response.announcements = _announcements_panel(db, user)
    if user.role is UserRole.STUDENT:
        response.student = _student_section(db, user, weights)
    if user.role in (UserRole.FACULTY, UserRole.RESEARCH_COORDINATOR):
        response.faculty = _faculty_section(db, user)
    if user.role is UserRole.RESEARCH_COORDINATOR:
        response.coordinator = _coordinator_section(db, user)
    if user.role is UserRole.DEAN_OF_RESEARCH:
        response.dean = _dean_section(db, user)
    if user.role is UserRole.FACILITY_CUSTODIAN:
        response.custodian = _custodian_section(db, user)
    if user.role is UserRole.ADMIN:
        response.admin = _admin_section(db)
    return response
