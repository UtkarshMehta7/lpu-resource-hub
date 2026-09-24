"""Pydantic schemas for student/researcher profiles.

verification_status/verified_by/verified_at are deliberately absent from
ResearcherProfileUpdate: never client-writable, only set by the researchers
module's verify action.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.profiles.models import ResearcherAvailability, VerificationStatus


class LinkItem(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=2000)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return value


class StudentProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    profile_type: str = "student"
    department_id: uuid.UUID | None = None
    department_locked: bool = False
    program: str
    year: int
    bio: str | None
    interests: str | None
    is_discoverable: bool
    created_at: datetime
    updated_at: datetime


class StudentProfileUpdate(BaseModel):
    program: str = Field(min_length=1, max_length=150)
    # Where you study. Self-declared, because someone who registered for
    # themselves has no department yet; an admin can correct it.
    department_id: uuid.UUID | None = None
    year: int = Field(ge=1, le=10)
    bio: str | None = Field(default=None, max_length=5000)
    interests: str | None = Field(default=None, max_length=2000)
    is_discoverable: bool = False


class ResearcherProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    profile_type: str = "researcher"
    department_id: uuid.UUID | None = None
    department_locked: bool = False
    designation: str
    bio: str | None
    availability: ResearcherAvailability
    links: list[LinkItem] | None
    verification_status: VerificationStatus
    verified_by: uuid.UUID | None
    verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResearcherProfileUpdate(BaseModel):
    designation: str = Field(min_length=1, max_length=150)
    # Self-declared, and only until a coordinator verifies the profile --
    # after that it is the institution's fact, not a claim, and only an admin
    # may change it.
    department_id: uuid.UUID | None = None
    bio: str | None = Field(default=None, max_length=5000)
    availability: ResearcherAvailability = ResearcherAvailability.AVAILABLE
    links: list[LinkItem] | None = None


class SkillEntry(BaseModel):
    skill_id: uuid.UUID
    proficiency: int = Field(ge=1, le=5)


class ResearchAreaEntry(BaseModel):
    research_area_id: uuid.UUID
    is_expertise: bool = False


class DepartmentCoordinatorRead(BaseModel):
    """Who oversees the viewer's department, and where to read about them.

    A faculty member needs to know who verifies their profile, reviews their
    projects and approves their bookings. Before this, the only way to find
    out was to ask someone.
    """

    department_id: uuid.UUID
    department_name: str
    #: None when the department has no coordinator yet -- which is worth
    #: saying out loud, because it explains why nothing is being verified.
    user_id: uuid.UUID | None = None
    full_name: str | None = None
    registration_number: str | None = None
    designation: str | None = None
    email: str | None = None
