"""Dashboard payloads.

One response with a section per role rather than four endpoints: the
sections a caller has no business seeing are simply absent (a coordinator
gets the faculty section too, because coordinators inherit faculty
abilities).
"""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel

from app.modules.audit.schemas import AuditLogRead
from app.modules.opportunities.schemas import OpportunityCard
from app.modules.projects.schemas import ProjectCard
from app.modules.researchers.schemas import VerificationQueueItem
from app.modules.researchers.search_schemas import ResearcherCard
from app.modules.users.models import UserRole


class DeadlineItem(BaseModel):
    opportunity_id: uuid.UUID
    title: str
    deadline: date
    applied: bool


class StudentDashboard(BaseModel):
    recommended_opportunities: list[OpportunityCard]
    recommended_projects: list[ProjectCard]
    recommended_researchers: list[ResearcherCard]
    saved_count: int
    applications_by_status: dict[str, int]
    pending_collaboration_requests: int
    upcoming_deadlines: list[DeadlineItem]


class FacultyDashboard(BaseModel):
    my_projects: list[ProjectCard]
    projects_by_status: dict[str, int]
    open_opportunities: list[OpportunityCard]
    pending_applications: int
    team_members: int
    accepted_collaborations: int
    publications: int
    pending_collaboration_requests: int


class CoordinatorDashboard(BaseModel):
    pending_verifications: list[VerificationQueueItem]
    pending_reviews: list[ProjectCard]
    open_reports: int
    # Activity in the coordinator's department over the last 30 days.
    department_activity: dict[str, int]


class AdminDashboard(BaseModel):
    users_by_role: dict[str, int]
    platform_counts: dict[str, int]
    open_reports: int
    recent_audit: list[AuditLogRead]


class DashboardResponse(BaseModel):
    role: UserRole
    onboarding_complete: bool
    student: StudentDashboard | None = None
    faculty: FacultyDashboard | None = None
    coordinator: CoordinatorDashboard | None = None
    admin: AdminDashboard | None = None
