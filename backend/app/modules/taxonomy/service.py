"""Skills, research areas, aliases and suggestions. Services never import FastAPI."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.taxonomy.models import (
    ResearchArea,
    Skill,
    TagAlias,
    TagSuggestion,
    TagSuggestionStatus,
    TagSuggestionType,
)
from app.modules.taxonomy.schemas import (
    ResearchAreaCreate,
    SkillCreate,
    TagAliasCreate,
    TagSuggestionCreate,
)

SEARCH_LIMIT = 50


class NameTakenError(Exception):
    """Raised when a skill/research-area/alias name is already in use."""


class SkillNotFoundError(Exception):
    """Raised when a referenced skill id does not exist."""


class ResearchAreaNotFoundError(Exception):
    """Raised when a referenced research area id does not exist."""


class ResearchAreaTooDeepError(Exception):
    """Raised when a research area's parent already has a parent (max 2 levels)."""


class TagSuggestionNotFoundError(Exception):
    """Raised when the target suggestion id does not exist."""


class TagSuggestionAlreadyReviewedError(Exception):
    """Raised when approving/rejecting a suggestion that is no longer PENDING."""


def search_skills(db: Session, q: str | None) -> list[Skill]:
    results: dict[uuid.UUID, Skill] = {}
    query = select(Skill).order_by(Skill.name).limit(SEARCH_LIMIT)
    if q:
        query = query.where(Skill.name.ilike(f"%{q}%"))
    for skill in db.execute(query).scalars():
        results[skill.id] = skill

    if q:
        canonical = _resolve_alias_skill(db, q)
        if canonical is not None:
            results[canonical.id] = canonical

    return list(results.values())


def _resolve_alias_skill(db: Session, q: str) -> Skill | None:
    alias = db.execute(
        select(TagAlias).where(func.lower(TagAlias.alias) == q.lower())
    ).scalar_one_or_none()
    if alias is None or alias.skill_id is None:
        return None
    return db.get(Skill, alias.skill_id)


def _resolve_alias_research_area(db: Session, q: str) -> ResearchArea | None:
    alias = db.execute(
        select(TagAlias).where(func.lower(TagAlias.alias) == q.lower())
    ).scalar_one_or_none()
    if alias is None or alias.research_area_id is None:
        return None
    return db.get(ResearchArea, alias.research_area_id)


def list_research_areas(
    db: Session, *, q: str | None = None, parent_id: uuid.UUID | None = None
) -> list[ResearchArea]:
    results: dict[uuid.UUID, ResearchArea] = {}
    query = select(ResearchArea).order_by(ResearchArea.name).limit(SEARCH_LIMIT)
    if parent_id is not None:
        query = query.where(ResearchArea.parent_id == parent_id)
    if q:
        query = query.where(ResearchArea.name.ilike(f"%{q}%"))
    for area in db.execute(query).scalars():
        results[area.id] = area

    if q:
        canonical = _resolve_alias_research_area(db, q)
        if canonical is not None:
            results[canonical.id] = canonical

    return list(results.values())


def create_skill(db: Session, data: SkillCreate) -> Skill:
    skill = Skill(name=data.name)
    db.add(skill)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise NameTakenError from exc
    db.refresh(skill)
    return skill


def create_research_area(db: Session, data: ResearchAreaCreate) -> ResearchArea:
    if data.parent_id is not None:
        parent = db.get(ResearchArea, data.parent_id)
        if parent is None:
            raise ResearchAreaNotFoundError
        if parent.parent_id is not None:
            raise ResearchAreaTooDeepError

    area = ResearchArea(name=data.name, parent_id=data.parent_id)
    db.add(area)
    db.commit()
    db.refresh(area)
    return area


def create_tag_alias(db: Session, data: TagAliasCreate) -> TagAlias:
    if data.skill_id is not None and db.get(Skill, data.skill_id) is None:
        raise SkillNotFoundError
    if data.research_area_id is not None and db.get(ResearchArea, data.research_area_id) is None:
        raise ResearchAreaNotFoundError

    alias = TagAlias(
        alias=data.alias, skill_id=data.skill_id, research_area_id=data.research_area_id
    )
    db.add(alias)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise NameTakenError from exc
    db.refresh(alias)
    return alias


def suggest_tag(db: Session, user_id: uuid.UUID, data: TagSuggestionCreate) -> TagSuggestion:
    suggestion = TagSuggestion(
        suggested_name=data.suggested_name,
        suggested_type=data.suggested_type,
        suggested_by=user_id,
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    return suggestion


def list_pending_suggestions(db: Session) -> list[TagSuggestion]:
    return list(
        db.execute(
            select(TagSuggestion)
            .where(TagSuggestion.status == TagSuggestionStatus.PENDING)
            .order_by(TagSuggestion.created_at)
        )
        .scalars()
        .all()
    )


def _get_suggestion_or_raise(db: Session, suggestion_id: uuid.UUID) -> TagSuggestion:
    suggestion = db.get(TagSuggestion, suggestion_id)
    if suggestion is None:
        raise TagSuggestionNotFoundError
    return suggestion


def approve_suggestion(
    db: Session, reviewer_id: uuid.UUID, suggestion_id: uuid.UUID
) -> TagSuggestion:
    suggestion = _get_suggestion_or_raise(db, suggestion_id)
    if suggestion.status is not TagSuggestionStatus.PENDING:
        raise TagSuggestionAlreadyReviewedError

    if suggestion.suggested_type is TagSuggestionType.SKILL:
        db.add(Skill(name=suggestion.suggested_name))
    else:
        db.add(ResearchArea(name=suggestion.suggested_name))

    suggestion.status = TagSuggestionStatus.APPROVED
    suggestion.reviewed_by = reviewer_id
    suggestion.reviewed_at = datetime.now(UTC)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise NameTakenError from exc
    db.refresh(suggestion)
    return suggestion


def reject_suggestion(
    db: Session, reviewer_id: uuid.UUID, suggestion_id: uuid.UUID
) -> TagSuggestion:
    suggestion = _get_suggestion_or_raise(db, suggestion_id)
    if suggestion.status is not TagSuggestionStatus.PENDING:
        raise TagSuggestionAlreadyReviewedError

    suggestion.status = TagSuggestionStatus.REJECTED
    suggestion.reviewed_by = reviewer_id
    suggestion.reviewed_at = datetime.now(UTC)
    db.commit()
    db.refresh(suggestion)
    return suggestion
