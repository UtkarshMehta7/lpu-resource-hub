"""Student/researcher profiles and skill/research-area assignments.

Services never import FastAPI; the router maps exceptions to HTTP status
codes.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.modules.profiles.models import (
    ResearcherProfile,
    StudentProfile,
    UserResearchArea,
    UserSkill,
    VerificationStatus,
)
from app.modules.profiles.schemas import (
    ResearchAreaEntry,
    ResearcherProfileUpdate,
    SkillEntry,
    StudentProfileUpdate,
)
from app.modules.taxonomy.models import ResearchArea, Skill
from app.modules.users.models import User, UserRole

MIN_ONBOARDING_ITEMS = 3


class ProfileNotFoundError(Exception):
    """Raised when no profile row exists yet for this user."""


class SkillNotFoundError(Exception):
    """Raised when a referenced skill id does not exist."""


class ResearchAreaNotFoundError(Exception):
    """Raised when a referenced research area id does not exist."""


def get_profile(db: Session, user: User) -> StudentProfile | ResearcherProfile:
    profile: StudentProfile | ResearcherProfile | None
    if user.role is UserRole.STUDENT:
        profile = db.get(StudentProfile, user.id)
    else:
        profile = db.get(ResearcherProfile, user.id)
    if profile is None:
        raise ProfileNotFoundError
    return profile


def upsert_student_profile(db: Session, user: User, data: StudentProfileUpdate) -> StudentProfile:
    profile = db.get(StudentProfile, user.id)
    if profile is None:
        profile = StudentProfile(user_id=user.id)
        db.add(profile)
    profile.program = data.program
    profile.year = data.year
    profile.bio = data.bio
    profile.interests = data.interests
    profile.is_discoverable = data.is_discoverable
    db.commit()
    db.refresh(profile)
    return profile


def upsert_researcher_profile(
    db: Session, user: User, data: ResearcherProfileUpdate
) -> ResearcherProfile:
    """Saving a researcher profile (re)submits it for coordinator review.

    There is no separate "submit" endpoint in the approved API surface, so
    this is what moves a profile into PENDING and puts it on the
    verification queue. An already-VERIFIED profile keeps its status:
    editing a bio should not silently revoke verification.
    """
    links = [item.model_dump() for item in data.links] if data.links is not None else None
    profile = db.get(ResearcherProfile, user.id)
    if profile is None:
        profile = ResearcherProfile(user_id=user.id, verification_status=VerificationStatus.PENDING)
        db.add(profile)
    elif profile.verification_status is not VerificationStatus.VERIFIED:
        profile.verification_status = VerificationStatus.PENDING
    profile.designation = data.designation
    profile.bio = data.bio
    profile.availability = data.availability
    profile.links = links
    db.commit()
    db.refresh(profile)
    return profile


def set_skills(db: Session, user_id: uuid.UUID, entries: list[SkillEntry]) -> list[UserSkill]:
    skill_ids = {entry.skill_id for entry in entries}
    if skill_ids:
        existing_ids = set(db.execute(select(Skill.id).where(Skill.id.in_(skill_ids))).scalars())
        if skill_ids - existing_ids:
            raise SkillNotFoundError

    db.execute(delete(UserSkill).where(UserSkill.user_id == user_id))
    rows = [
        UserSkill(user_id=user_id, skill_id=entry.skill_id, proficiency=entry.proficiency)
        for entry in entries
    ]
    db.add_all(rows)
    db.flush()
    _recompute_onboarding_complete(db, user_id)
    db.commit()
    return rows


def set_research_areas(
    db: Session, user_id: uuid.UUID, entries: list[ResearchAreaEntry]
) -> list[UserResearchArea]:
    area_ids = {entry.research_area_id for entry in entries}
    if area_ids:
        existing_ids = set(
            db.execute(select(ResearchArea.id).where(ResearchArea.id.in_(area_ids))).scalars()
        )
        if area_ids - existing_ids:
            raise ResearchAreaNotFoundError

    db.execute(delete(UserResearchArea).where(UserResearchArea.user_id == user_id))
    rows = [
        UserResearchArea(
            user_id=user_id,
            research_area_id=entry.research_area_id,
            is_expertise=entry.is_expertise,
        )
        for entry in entries
    ]
    db.add_all(rows)
    db.flush()
    _recompute_onboarding_complete(db, user_id)
    db.commit()
    return rows


def _recompute_onboarding_complete(db: Session, user_id: uuid.UUID) -> None:
    skill_count = db.execute(
        select(func.count()).select_from(UserSkill).where(UserSkill.user_id == user_id)
    ).scalar_one()
    area_count = db.execute(
        select(func.count())
        .select_from(UserResearchArea)
        .where(UserResearchArea.user_id == user_id)
    ).scalar_one()
    complete = skill_count >= MIN_ONBOARDING_ITEMS and area_count >= MIN_ONBOARDING_ITEMS
    db.execute(update(User).where(User.id == user_id).values(onboarding_complete=complete))
