"""Public directory schemas.

These are the first schemas that expose *other people's* data, so they carry
only public fields. Email is deliberately absent -- the coordinator
verification queue (a scoped review view, not a public one) is the only
place it appears.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.modules.profiles.models import ResearcherAvailability, VerificationStatus
from app.modules.profiles.schemas import LinkItem
from app.modules.projects.schemas import ProjectCard


class ResearcherCard(BaseModel):
    user_id: uuid.UUID
    full_name: str
    designation: str
    department_id: uuid.UUID | None
    availability: ResearcherAvailability
    verification_status: VerificationStatus
    research_areas: list[str]
    skills: list[str]


class ResearcherDetail(ResearcherCard):
    bio: str | None
    links: list[LinkItem] | None
    created_at: datetime


class StudentCard(BaseModel):
    """Only ever built for students with is_discoverable = true."""

    user_id: uuid.UUID
    full_name: str
    program: str
    year: int
    department_id: uuid.UUID | None
    interests: str | None
    research_areas: list[str]
    skills: list[str]


class SearchResults(BaseModel):
    """Unified search. Later steps add projects, publications and so on."""

    query: str
    researchers: list[ResearcherCard]
    projects: list[ProjectCard]
