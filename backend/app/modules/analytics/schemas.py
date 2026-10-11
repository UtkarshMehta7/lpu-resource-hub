"""Dashboard payloads.

One response with a section per role rather than four endpoints: the
sections a caller has no business seeing are simply absent (a coordinator
gets the faculty section too, because coordinators inherit faculty
abilities).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.modules.announcements.schemas import AnnouncementRead
from app.modules.audit.schemas import AuditLogRead
from app.modules.opportunities.schemas import OpportunityCard
from app.modules.projects.schemas import ProjectCard
from app.modules.researchers.schemas import VerificationQueueItem
from app.modules.researchers.search_schemas import ResearcherCard
from app.modules.users.models import UserRole


class DeadlineItem(BaseModel):
    """Something the viewer saved or applied to that is closing soon."""

    kind: Literal["opportunity", "funding"]
    item_id: uuid.UUID
    title: str
    deadline: date
    # Only meaningful for opportunities: saved-but-not-applied still shows up.
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


class DeanDashboard(BaseModel):
    """What a Dean of Research opens the platform to see.

    The dashboard had sections for student, faculty, coordinator and admin and
    none for a dean, so the role signed in to an empty page. These are the
    institution-wide figures that decide where attention goes, each one a
    number the dean can then act on -- the at-risk board, the review queue,
    the department comparison.
    """

    departments: int
    departments_needing_attention: int
    projects_at_risk: int
    pending_cross_department_reviews: int
    verification_backlog: int
    active_projects: int
    researchers: int


class CustodianDashboard(BaseModel):
    """The rooms this person looks after, and what is waiting on them."""

    facilities_held: int
    equipment: int
    bookings_awaiting_decision: int


class AdminDashboard(BaseModel):
    users_by_role: dict[str, int]
    platform_counts: dict[str, int]
    open_reports: int
    recent_audit: list[AuditLogRead]


class AnnouncementsPanel(BaseModel):
    """The notice board as it appears on a dashboard.

    Present for EVERY role, outside the per-role dispatch below: a notice is
    the one thing on this platform addressed to everybody, so the panel is not
    something a role either has or lacks. The searchable history lives at
    /announcements; this is the "what has been said lately" everybody meets
    when they sign in.
    """

    unread: int
    #: Newest first. Published only -- a draft of your own is not news.
    latest: list[AnnouncementRead]


class DashboardResponse(BaseModel):
    role: UserRole
    onboarding_complete: bool
    #: Every role gets one. Defaults to empty rather than None so a reader
    #: never has to branch on whether the board exists.
    announcements: AnnouncementsPanel = AnnouncementsPanel(unread=0, latest=[])
    student: StudentDashboard | None = None
    faculty: FacultyDashboard | None = None
    coordinator: CoordinatorDashboard | None = None
    dean: DeanDashboard | None = None
    custodian: CustodianDashboard | None = None
    admin: AdminDashboard | None = None
