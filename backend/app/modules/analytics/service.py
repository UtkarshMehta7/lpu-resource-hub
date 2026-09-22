"""Dashboard aggregates.

Every count here is scoped the same way the corresponding list endpoint is:
a coordinator's numbers cover their department, a faculty member's cover
their own work. Nothing aggregates across a boundary the caller couldn't
browse item by item.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.ml.features import ScoreWeights
from app.modules.admin.models import Department, School
from app.modules.analytics.schemas import (
    AdminDashboard,
    CoordinatorDashboard,
    DashboardResponse,
    DeadlineItem,
    FacultyDashboard,
    StudentDashboard,
)
from app.modules.applications.models import Application, ApplicationStatus
from app.modules.audit.models import AuditLog
from app.modules.audit.schemas import AuditLogRead
from app.modules.collaborations.models import CollaborationRequest, CollaborationStatus
from app.modules.funding.models import FundingOpportunity, FundingStatus
from app.modules.opportunities.models import Opportunity, OpportunityStatus
from app.modules.opportunities.schemas import OpportunityCard
from app.modules.opportunities.service import opportunity_cards
from app.modules.profiles.models import ResearcherProfile, SavedItem, StudentProfile
from app.modules.projects.models import Project, ProjectMember, ProjectStatus
from app.modules.projects.schemas import ProjectCard
from app.modules.projects.service import project_cards, review_queue
from app.modules.publications.models import Publication, PublicationAuthor
from app.modules.recommendations.schemas import TargetType
from app.modules.recommendations.service import recommend
from app.modules.reports.models import ContentReport, ReportStatus
from app.modules.researchers.search_schemas import ResearcherCard
from app.modules.researchers.service import list_verification_queue, to_queue_item
from app.modules.users.models import CoordinatorScopeType, User, UserRole

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


def dashboard(db: Session, user: User, weights: ScoreWeights) -> DashboardResponse:
    response = DashboardResponse(role=user.role, onboarding_complete=user.onboarding_complete)
    if user.role is UserRole.STUDENT:
        response.student = _student_section(db, user, weights)
    if user.role in (UserRole.FACULTY, UserRole.RESEARCH_COORDINATOR):
        response.faculty = _faculty_section(db, user)
    if user.role is UserRole.RESEARCH_COORDINATOR:
        response.coordinator = _coordinator_section(db, user)
    if user.role is UserRole.ADMIN:
        response.admin = _admin_section(db)
    return response
