"""Taxonomy endpoints: public search/read, coordinator+admin manage, tag suggestions.

Routes don't share one path prefix (/skills, /research-areas, /taxonomy/...,
/tags/suggestions, /admin/tag-suggestions), so this is one router with full
paths per route rather than several tiny prefix-scoped routers.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import Permission, require_permission
from app.db.session import get_db
from app.modules.taxonomy.schemas import (
    ResearchAreaCreate,
    ResearchAreaRead,
    SkillCreate,
    SkillRead,
    TagAliasCreate,
    TagAliasRead,
    TagSuggestionCreate,
    TagSuggestionRead,
)
from app.modules.taxonomy.service import (
    NameTakenError,
    ResearchAreaNotFoundError,
    ResearchAreaTooDeepError,
    SkillNotFoundError,
    TagSuggestionAlreadyReviewedError,
    TagSuggestionNotFoundError,
    approve_suggestion,
    create_research_area,
    create_skill,
    create_tag_alias,
    list_pending_suggestions,
    list_research_areas,
    reject_suggestion,
    search_skills,
    suggest_tag,
)
from app.modules.users.models import User

router = APIRouter(tags=["taxonomy"])


@router.get("/skills", response_model=list[SkillRead], dependencies=[Depends(get_current_user)])
def read_skills(db: Annotated[Session, Depends(get_db)], q: str | None = None) -> list[SkillRead]:
    return [SkillRead.model_validate(s) for s in search_skills(db, q)]


@router.get(
    "/research-areas",
    response_model=list[ResearchAreaRead],
    dependencies=[Depends(get_current_user)],
)
def read_research_areas(
    db: Annotated[Session, Depends(get_db)],
    q: str | None = None,
    parent_id: uuid.UUID | None = None,
) -> list[ResearchAreaRead]:
    areas = list_research_areas(db, q=q, parent_id=parent_id)
    return [ResearchAreaRead.model_validate(a) for a in areas]


@router.post(
    "/taxonomy/skills",
    response_model=SkillRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.TAXONOMY_MANAGE))],
)
def create_skill_route(data: SkillCreate, db: Annotated[Session, Depends(get_db)]) -> SkillRead:
    try:
        return SkillRead.model_validate(create_skill(db, data))
    except NameTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A skill with this name already exists."
        ) from exc


@router.post(
    "/taxonomy/research-areas",
    response_model=ResearchAreaRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.TAXONOMY_MANAGE))],
)
def create_research_area_route(
    data: ResearchAreaCreate, db: Annotated[Session, Depends(get_db)]
) -> ResearchAreaRead:
    try:
        return ResearchAreaRead.model_validate(create_research_area(db, data))
    except ResearchAreaNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Parent research area not found."
        ) from exc
    except ResearchAreaTooDeepError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Research areas can be nested at most two levels deep.",
        ) from exc


@router.post(
    "/taxonomy/aliases",
    response_model=TagAliasRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.TAXONOMY_MANAGE))],
)
def create_tag_alias_route(
    data: TagAliasCreate, db: Annotated[Session, Depends(get_db)]
) -> TagAliasRead:
    try:
        return TagAliasRead.model_validate(create_tag_alias(db, data))
    except (SkillNotFoundError, ResearchAreaNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alias target not found."
        ) from exc
    except NameTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This alias already exists."
        ) from exc


@router.post(
    "/tags/suggestions", response_model=TagSuggestionRead, status_code=status.HTTP_201_CREATED
)
def create_tag_suggestion(
    data: TagSuggestionCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TagSuggestionRead:
    return TagSuggestionRead.model_validate(suggest_tag(db, current_user.id, data))


@router.get(
    "/admin/tag-suggestions",
    response_model=list[TagSuggestionRead],
    dependencies=[Depends(require_permission(Permission.TAXONOMY_MANAGE))],
)
def read_pending_suggestions(
    db: Annotated[Session, Depends(get_db)],
) -> list[TagSuggestionRead]:
    return [TagSuggestionRead.model_validate(s) for s in list_pending_suggestions(db)]


@router.post(
    "/admin/tag-suggestions/{suggestion_id}/approve",
    response_model=TagSuggestionRead,
)
def approve_suggestion_route(
    suggestion_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    reviewer: Annotated[User, Depends(require_permission(Permission.TAXONOMY_MANAGE))],
) -> TagSuggestionRead:
    try:
        return TagSuggestionRead.model_validate(approve_suggestion(db, reviewer.id, suggestion_id))
    except TagSuggestionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found."
        ) from exc
    except TagSuggestionAlreadyReviewedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This suggestion was already reviewed."
        ) from exc
    except NameTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A skill or research area with this name already exists.",
        ) from exc


@router.post(
    "/admin/tag-suggestions/{suggestion_id}/reject",
    response_model=TagSuggestionRead,
)
def reject_suggestion_route(
    suggestion_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    reviewer: Annotated[User, Depends(require_permission(Permission.TAXONOMY_MANAGE))],
) -> TagSuggestionRead:
    try:
        return TagSuggestionRead.model_validate(reject_suggestion(db, reviewer.id, suggestion_id))
    except TagSuggestionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found."
        ) from exc
    except TagSuggestionAlreadyReviewedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This suggestion was already reviewed."
        ) from exc
