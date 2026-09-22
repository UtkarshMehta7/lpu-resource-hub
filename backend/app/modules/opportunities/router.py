"""Opportunity endpoints, mounted under /api/v1.

404 when the caller must not know it exists (someone else's draft), 403
when they can see it but may not act, 409 when the action isn't valid from
the current status (or the deadline has passed), 422 for bad input.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.pagination import Page, PageParams
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import client_ip, enforce_search_rate_limit
from app.db.session import get_db
from app.modules.opportunities import service
from app.modules.opportunities.models import OpportunityStatus, OpportunityType
from app.modules.opportunities.policies import InvalidTransitionError, NotOwnerError
from app.modules.opportunities.schemas import (
    OpportunityCard,
    OpportunityCreate,
    OpportunityRead,
    OpportunityUpdate,
)
from app.modules.search.models import EntityType
from app.modules.search.tasks import schedule_embedding
from app.modules.users.models import User

router = APIRouter(tags=["opportunities"])

CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]

_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    service.OpportunityNotFoundError: (status.HTTP_404_NOT_FOUND, "Opportunity not found."),
    service.ProjectNotFoundError: (status.HTTP_404_NOT_FOUND, "Project not found."),
    NotOwnerError: (status.HTTP_403_FORBIDDEN, "You can't manage this opportunity."),
    service.NotProjectOwnerError: (
        status.HTTP_403_FORBIDDEN,
        "You can only post opportunities on your own projects.",
    ),
    InvalidTransitionError: (
        status.HTTP_409_CONFLICT,
        "That action isn't allowed while the opportunity is in its current status.",
    ),
    service.ProjectNotActiveError: (
        status.HTTP_409_CONFLICT,
        "Opportunities can only be posted on active projects.",
    ),
    service.DeadlinePassedError: (status.HTTP_409_CONFLICT, "The deadline has passed."),
    service.ProjectRequiredError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Choose one of your active projects for this opportunity.",
    ),
    service.UnknownSkillError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "One or more skills do not exist.",
    ),
    service.InvalidDeadlineError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "The deadline can't be in the past.",
    ),
    service.PositionsBelowAcceptedError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "positions can't be lower than the number of accepted applicants.",
    ),
}


@contextmanager
def _domain_errors() -> Iterator[None]:
    try:
        yield
    except tuple(_ERROR_MAP) as exc:
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from exc


@router.get(
    "/opportunities",
    response_model=Page[OpportunityCard],
    dependencies=[Depends(enforce_search_rate_limit)],
)
def read_opportunities(
    db: DbSession,
    viewer: CurrentUser,
    params: Annotated[PageParams, Depends()],
    q: str | None = None,
    opportunity_type: Annotated[OpportunityType | None, Query(alias="type")] = None,
    status_filter: Annotated[OpportunityStatus | None, Query(alias="status")] = None,
    department_id: uuid.UUID | None = None,
    skill_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    deadline_after: date | None = None,
    deadline_before: date | None = None,
    mine: bool = False,
) -> Page[OpportunityCard]:
    return service.list_opportunities(
        db,
        viewer,
        params,
        q=q,
        opportunity_type=opportunity_type,
        status=status_filter,
        department_id=department_id,
        skill_id=skill_id,
        project_id=project_id,
        deadline_after=deadline_after,
        deadline_before=deadline_before,
        mine=mine,
    )


@router.post("/opportunities", response_model=OpportunityRead, status_code=status.HTTP_201_CREATED)
def create_opportunity(
    data: OpportunityCreate,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    creator: Annotated[User, Depends(require_permission(Permission.OPPORTUNITY_CREATE))],
) -> OpportunityRead:
    with _domain_errors():
        opportunity = service.create_opportunity(db, creator, data)
    schedule_embedding(request, background, EntityType.OPPORTUNITY, opportunity.id)
    return opportunity


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityRead)
def read_opportunity(
    opportunity_id: uuid.UUID, db: DbSession, viewer: CurrentUser
) -> OpportunityRead:
    with _domain_errors():
        return service.get_opportunity(db, viewer, opportunity_id)


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityRead)
def update_opportunity(
    opportunity_id: uuid.UUID,
    data: OpportunityUpdate,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    actor: CurrentUser,
) -> OpportunityRead:
    with _domain_errors():
        opportunity = service.update_opportunity(db, actor, opportunity_id, data)
    schedule_embedding(request, background, EntityType.OPPORTUNITY, opportunity.id)
    return opportunity


@router.post("/opportunities/{opportunity_id}/publish", response_model=OpportunityRead)
def publish_opportunity(
    opportunity_id: uuid.UUID, db: DbSession, actor: CurrentUser
) -> OpportunityRead:
    with _domain_errors():
        return service.publish_opportunity(db, actor, opportunity_id)


@router.post("/opportunities/{opportunity_id}/close", response_model=OpportunityRead)
def close_opportunity(
    opportunity_id: uuid.UUID, request: Request, db: DbSession, actor: CurrentUser
) -> OpportunityRead:
    with _domain_errors():
        return service.close_opportunity(db, actor, opportunity_id, ip=client_ip(request))
