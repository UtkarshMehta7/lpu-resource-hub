"""Funding call endpoints, mounted under /api/v1.

Readable by every signed-in user; managed by coordinators and admins
(funding is university-wide, so there's no department scope here).
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
from app.core.rate_limit import enforce_search_rate_limit
from app.db.session import get_db
from app.modules.funding import service
from app.modules.funding.models import FundingStatus
from app.modules.funding.schemas import FundingCreate, FundingRead, FundingUpdate
from app.modules.search.models import EntityType
from app.modules.search.tasks import schedule_embedding
from app.modules.users.models import User

router = APIRouter(tags=["funding"])

DbSession = Annotated[Session, Depends(get_db)]
Manager = Annotated[User, Depends(require_permission(Permission.FUNDING_MANAGE))]

_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    service.FundingNotFoundError: (status.HTTP_404_NOT_FOUND, "Funding call not found."),
    service.UnknownResearchAreaError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "One or more research areas do not exist.",
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
    "/funding",
    response_model=Page[FundingRead],
    dependencies=[Depends(get_current_user), Depends(enforce_search_rate_limit)],
)
def read_funding_list(
    db: DbSession,
    params: Annotated[PageParams, Depends()],
    q: str | None = None,
    status_filter: Annotated[FundingStatus | None, Query(alias="status")] = None,
    research_area_id: uuid.UUID | None = None,
    deadline_before: date | None = None,
    open_only: bool = False,
) -> Page[FundingRead]:
    return service.list_funding(
        db,
        params,
        q=q,
        status=status_filter,
        research_area_id=research_area_id,
        deadline_before=deadline_before,
        open_only=open_only,
    )


@router.post("/funding", response_model=FundingRead, status_code=status.HTTP_201_CREATED)
def create_funding(
    data: FundingCreate,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    actor: Manager,
) -> FundingRead:
    with _domain_errors():
        funding = service.create_funding(db, actor, data)
    schedule_embedding(request, background, EntityType.FUNDING, funding.id)
    return funding


@router.get("/funding/{funding_id}", response_model=FundingRead)
def read_funding(
    funding_id: uuid.UUID, db: DbSession, viewer: Annotated[User, Depends(get_current_user)]
) -> FundingRead:
    with _domain_errors():
        return service.get_funding(db, funding_id)


@router.patch("/funding/{funding_id}", response_model=FundingRead)
def update_funding(
    funding_id: uuid.UUID, data: FundingUpdate, db: DbSession, actor: Manager
) -> FundingRead:
    with _domain_errors():
        return service.update_funding(db, funding_id, data)


@router.delete("/funding/{funding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_funding(funding_id: uuid.UUID, db: DbSession, actor: Manager) -> None:
    with _domain_errors():
        service.delete_funding(db, funding_id)
