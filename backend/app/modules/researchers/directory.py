"""Researcher directory, student discovery and unified search queries.

Text matching combines two things in one pass: the weighted tsvector
(`search_document @@ websearch_to_tsquery`) for real term matching, and a
pg_trgm similarity match on the name so a misspelled name still finds the
person. Results rank by ts_rank first, then name similarity.

Services never import FastAPI.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Literal

from sqlalchemy import ColumnElement, Row, Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams
from app.modules.admin.models import Department
from app.modules.profiles.models import (
    ResearcherAvailability,
    ResearcherProfile,
    StudentProfile,
    UserResearchArea,
    UserSkill,
    VerificationStatus,
)
from app.modules.researchers.search_schemas import (
    ResearcherCard,
    ResearcherDetail,
    StudentCard,
)
from app.modules.taxonomy.models import ResearchArea, Skill
from app.modules.users.models import User

SortOption = Literal["name", "-name", "recent"]

# Below this, a trigram name match is noise rather than a helpful typo fix.
NAME_SIMILARITY_THRESHOLD = 0.3


class ResearcherNotFoundError(Exception):
    """Raised when a user id has no researcher profile."""


def _text_filter(q: str) -> ColumnElement[bool]:
    tsquery = func.websearch_to_tsquery("english", q)
    return or_(
        ResearcherProfile.search_document.op("@@")(tsquery),
        func.similarity(User.full_name, q) > NAME_SIMILARITY_THRESHOLD,
    )


def _apply_researcher_filters(
    query: Select[tuple[User, ResearcherProfile]],
    *,
    q: str | None,
    school_id: uuid.UUID | None,
    department_id: uuid.UUID | None,
    research_area_id: uuid.UUID | None,
    skill_id: uuid.UUID | None,
    availability: ResearcherAvailability | None,
    verified_only: bool,
) -> Select[tuple[User, ResearcherProfile]]:
    if q:
        query = query.where(_text_filter(q))
    if school_id is not None:
        query = query.where(
            User.department_id.in_(select(Department.id).where(Department.school_id == school_id))
        )
    if department_id is not None:
        query = query.where(User.department_id == department_id)
    if research_area_id is not None:
        # A parent area also matches its children, so filtering by
        # "Artificial Intelligence" finds people tagged "Machine Learning".
        area_ids = select(ResearchArea.id).where(
            or_(
                ResearchArea.id == research_area_id,
                ResearchArea.parent_id == research_area_id,
            )
        )
        query = query.where(
            select(UserResearchArea.user_id)
            .where(
                UserResearchArea.user_id == User.id,
                UserResearchArea.research_area_id.in_(area_ids),
            )
            .exists()
        )
    if skill_id is not None:
        query = query.where(
            select(UserSkill.user_id)
            .where(UserSkill.user_id == User.id, UserSkill.skill_id == skill_id)
            .exists()
        )
    if availability is not None:
        query = query.where(ResearcherProfile.availability == availability)
    if verified_only:
        query = query.where(ResearcherProfile.verification_status == VerificationStatus.VERIFIED)
    return query


def _tags_by_user(
    db: Session, user_ids: Sequence[uuid.UUID]
) -> tuple[dict[uuid.UUID, list[str]], dict[uuid.UUID, list[str]]]:
    """Two aggregate queries instead of N+1 per card."""
    if not user_ids:
        return {}, {}

    areas: dict[uuid.UUID, list[str]] = {}
    for user_id, name in db.execute(
        select(UserResearchArea.user_id, ResearchArea.name)
        .join(ResearchArea, ResearchArea.id == UserResearchArea.research_area_id)
        .where(UserResearchArea.user_id.in_(user_ids))
        .order_by(ResearchArea.name)
    ):
        areas.setdefault(user_id, []).append(name)

    skills: dict[uuid.UUID, list[str]] = {}
    for user_id, name in db.execute(
        select(UserSkill.user_id, Skill.name)
        .join(Skill, Skill.id == UserSkill.skill_id)
        .where(UserSkill.user_id.in_(user_ids))
        .order_by(Skill.name)
    ):
        skills.setdefault(user_id, []).append(name)

    return areas, skills


def _to_cards(
    db: Session, rows: Sequence[Row[tuple[User, ResearcherProfile]]]
) -> list[ResearcherCard]:
    user_ids = [row[0].id for row in rows]
    areas, skills = _tags_by_user(db, user_ids)
    return [
        ResearcherCard(
            user_id=user.id,
            full_name=user.full_name,
            designation=profile.designation,
            department_id=user.department_id,
            availability=profile.availability,
            verification_status=profile.verification_status,
            research_areas=areas.get(user.id, []),
            skills=skills.get(user.id, []),
        )
        for user, profile in rows
    ]


def list_researchers(
    db: Session,
    params: PageParams,
    *,
    q: str | None = None,
    school_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    research_area_id: uuid.UUID | None = None,
    skill_id: uuid.UUID | None = None,
    availability: ResearcherAvailability | None = None,
    verified_only: bool = False,
    sort: SortOption = "name",
) -> Page[ResearcherCard]:
    query = select(User, ResearcherProfile).join(
        ResearcherProfile, ResearcherProfile.user_id == User.id
    )
    query = query.where(User.is_active.is_(True))
    query = _apply_researcher_filters(
        query,
        q=q,
        school_id=school_id,
        department_id=department_id,
        research_area_id=research_area_id,
        skill_id=skill_id,
        availability=availability,
        verified_only=verified_only,
    )

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()

    if q:
        # Relevance first when there's a query: exact term hits above fuzzy
        # name matches, then alphabetical for stable paging.
        tsquery = func.websearch_to_tsquery("english", q)
        query = query.order_by(
            func.ts_rank(ResearcherProfile.search_document, tsquery).desc(),
            func.similarity(User.full_name, q).desc(),
            User.full_name,
        )
    elif sort == "-name":
        query = query.order_by(User.full_name.desc())
    elif sort == "recent":
        query = query.order_by(ResearcherProfile.created_at.desc())
    else:
        query = query.order_by(User.full_name)

    rows = db.execute(query.offset(params.offset).limit(params.page_size)).all()
    return Page[ResearcherCard](
        items=_to_cards(db, rows),
        page=params.page,
        page_size=params.page_size,
        total=total,
    )


def get_researcher(db: Session, user_id: uuid.UUID) -> ResearcherDetail:
    row = db.execute(
        select(User, ResearcherProfile)
        .join(ResearcherProfile, ResearcherProfile.user_id == User.id)
        .where(User.id == user_id, User.is_active.is_(True))
    ).first()
    if row is None:
        raise ResearcherNotFoundError

    user, profile = row
    areas, skills = _tags_by_user(db, [user.id])
    return ResearcherDetail(
        user_id=user.id,
        full_name=user.full_name,
        designation=profile.designation,
        department_id=user.department_id,
        availability=profile.availability,
        verification_status=profile.verification_status,
        research_areas=areas.get(user.id, []),
        skills=skills.get(user.id, []),
        bio=profile.bio,
        links=profile.links,
        created_at=profile.created_at,
    )


def list_discoverable_students(
    db: Session,
    params: PageParams,
    *,
    q: str | None = None,
    department_id: uuid.UUID | None = None,
) -> Page[StudentCard]:
    """Only students who opted in. The is_discoverable filter is applied in
    the query itself, so a non-discoverable student can never leak out."""
    query = (
        select(User, StudentProfile)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .where(User.is_active.is_(True), StudentProfile.is_discoverable.is_(True))
    )
    if q:
        query = query.where(
            or_(
                User.full_name.ilike(f"%{q}%"),
                StudentProfile.program.ilike(f"%{q}%"),
                StudentProfile.interests.ilike(f"%{q}%"),
            )
        )
    if department_id is not None:
        query = query.where(User.department_id == department_id)

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(
        query.order_by(User.full_name).offset(params.offset).limit(params.page_size)
    ).all()

    user_ids = [row[0].id for row in rows]
    areas, skills = _tags_by_user(db, user_ids)
    return Page[StudentCard](
        items=[
            StudentCard(
                user_id=user.id,
                full_name=user.full_name,
                program=profile.program,
                year=profile.year,
                department_id=user.department_id,
                interests=profile.interests,
                research_areas=areas.get(user.id, []),
                skills=skills.get(user.id, []),
            )
            for user, profile in rows
        ],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )
