"""Publication endpoints, mounted under /api/v1.

Publications are readable by every signed-in user. Only the creator may edit
one; the creator or an admin may delete it. Linked projects the viewer can't
see are omitted from responses rather than erroring.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.pagination import Page, PageParams
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import client_ip, enforce_search_rate_limit
from app.db.session import get_db
from app.modules.publications import service
from app.modules.publications.schemas import (
    PublicationCreate,
    PublicationRead,
    PublicationUpdate,
)
from app.modules.search.models import EntityType
from app.modules.search.tasks import schedule_embedding
from app.modules.users.models import User

router = APIRouter(tags=["publications"])

CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]

_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    service.PublicationNotFoundError: (status.HTTP_404_NOT_FOUND, "Publication not found."),
    service.NotCreatorError: (
        status.HTTP_403_FORBIDDEN,
        "Only the publication's creator can do this.",
    ),
    service.DuplicateDoiError: (
        status.HTTP_409_CONFLICT,
        "A publication with this DOI already exists.",
    ),
    service.UnknownAuthorError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "One or more authors do not name an active user.",
    ),
    service.ProjectLinkError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "You can only link publications to projects you own or belong to.",
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
    "/publications",
    response_model=Page[PublicationRead],
    dependencies=[Depends(enforce_search_rate_limit)],
)
def read_publications(
    db: DbSession,
    viewer: CurrentUser,
    params: Annotated[PageParams, Depends()],
    q: str | None = None,
    author_id: uuid.UUID | None = None,
    year: int | None = None,
    project_id: uuid.UUID | None = None,
    research_area_id: uuid.UUID | None = None,
) -> Page[PublicationRead]:
    return service.list_publications(
        db,
        viewer,
        params,
        q=q,
        author_id=author_id,
        year=year,
        project_id=project_id,
        research_area_id=research_area_id,
    )


@router.post("/publications", response_model=PublicationRead, status_code=status.HTTP_201_CREATED)
def create_publication(
    data: PublicationCreate,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    creator: Annotated[User, Depends(require_permission(Permission.PUBLICATION_CREATE))],
) -> PublicationRead:
    with _domain_errors():
        publication = service.create_publication(db, creator, data)
    schedule_embedding(request, background, EntityType.PUBLICATION, publication.id)
    return publication


@router.get("/publications/{publication_id}", response_model=PublicationRead)
def read_publication(
    publication_id: uuid.UUID, db: DbSession, viewer: CurrentUser
) -> PublicationRead:
    with _domain_errors():
        return service.get_publication(db, viewer, publication_id)


@router.patch("/publications/{publication_id}", response_model=PublicationRead)
def update_publication(
    publication_id: uuid.UUID, data: PublicationUpdate, db: DbSession, actor: CurrentUser
) -> PublicationRead:
    with _domain_errors():
        return service.update_publication(db, actor, publication_id, data)


@router.delete("/publications/{publication_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_publication(
    publication_id: uuid.UUID, request: Request, db: DbSession, actor: CurrentUser
) -> None:
    with _domain_errors():
        service.delete_publication(db, actor, publication_id, ip=client_ip(request))
