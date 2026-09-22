"""Research project endpoints, mounted under /api/v1.

Status codes: 404 when the caller must not know the project exists (drafts
of other people, other departments), 403 when they can see it but may not
act (not the owner, reviewing their own project, unverified submitter), 409
when the action isn't a valid transition from the current status.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.pagination import Page, PageParams
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import client_ip, enforce_search_rate_limit
from app.db.session import get_db
from app.modules.projects import service
from app.modules.projects.models import ProjectStatus
from app.modules.projects.policies import InvalidTransitionError, NotOwnerError, SelfReviewError
from app.modules.projects.schemas import (
    MemberCreate,
    MemberRead,
    ProjectCard,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    ReviewRequest,
)
from app.modules.users.models import User

router = APIRouter(tags=["projects"])

CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]

_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    service.ProjectNotFoundError: (status.HTTP_404_NOT_FOUND, "Project not found."),
    NotOwnerError: (status.HTTP_403_FORBIDDEN, "Only the project owner can do this."),
    SelfReviewError: (status.HTTP_403_FORBIDDEN, "You cannot review your own project."),
    service.OwnerNotVerifiedError: (
        status.HTTP_403_FORBIDDEN,
        "Your researcher profile must be verified before you can submit a project.",
    ),
    InvalidTransitionError: (
        status.HTTP_409_CONFLICT,
        "That action isn't allowed while the project is in its current status.",
    ),
    service.UnknownTagError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "One or more skills or research areas do not exist.",
    ),
    service.InvalidDateRangeError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "start_date must be on or before end_date.",
    ),
    service.MemberNotFoundError: (status.HTTP_404_NOT_FOUND, "User or member not found."),
    service.DuplicateMemberError: (
        status.HTTP_409_CONFLICT,
        "That user is already a member of this project.",
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
    "/projects",
    response_model=Page[ProjectCard],
    dependencies=[Depends(enforce_search_rate_limit)],
)
def read_projects(
    db: DbSession,
    viewer: CurrentUser,
    params: Annotated[PageParams, Depends()],
    q: str | None = None,
    status_filter: Annotated[ProjectStatus | None, Query(alias="status")] = None,
    department_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    research_area_id: uuid.UUID | None = None,
    skill_id: uuid.UUID | None = None,
    mine: bool = False,
) -> Page[ProjectCard]:
    return service.list_projects(
        db,
        viewer,
        params,
        q=q,
        status=status_filter,
        department_id=department_id,
        owner_id=owner_id,
        research_area_id=research_area_id,
        skill_id=skill_id,
        mine=mine,
    )


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    db: DbSession,
    owner: Annotated[User, Depends(require_permission(Permission.PROJECT_CREATE))],
) -> ProjectRead:
    with _domain_errors():
        return service.create_project(db, owner, data)


@router.get("/projects/{project_id}", response_model=ProjectRead)
def read_project(project_id: uuid.UUID, db: DbSession, viewer: CurrentUser) -> ProjectRead:
    with _domain_errors():
        return service.get_project(db, viewer, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: uuid.UUID, data: ProjectUpdate, db: DbSession, actor: CurrentUser
) -> ProjectRead:
    with _domain_errors():
        return service.update_project(db, actor, project_id, data)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID, request: Request, db: DbSession, actor: CurrentUser
) -> None:
    with _domain_errors():
        service.delete_project(db, actor, project_id, ip=client_ip(request))


@router.post("/projects/{project_id}/submit", response_model=ProjectRead)
def submit_project(project_id: uuid.UUID, db: DbSession, actor: CurrentUser) -> ProjectRead:
    with _domain_errors():
        return service.submit_project(db, actor, project_id)


@router.post("/projects/{project_id}/review", response_model=ProjectRead)
def review_project(
    project_id: uuid.UUID,
    data: ReviewRequest,
    request: Request,
    db: DbSession,
    reviewer: Annotated[User, Depends(require_permission(Permission.PROJECT_REVIEW))],
) -> ProjectRead:
    with _domain_errors():
        return service.review_project(db, reviewer, project_id, data, ip=client_ip(request))


@router.post("/projects/{project_id}/complete", response_model=ProjectRead)
def complete_project(project_id: uuid.UUID, db: DbSession, actor: CurrentUser) -> ProjectRead:
    with _domain_errors():
        return service.complete_project(db, actor, project_id)


@router.post("/projects/{project_id}/archive", response_model=ProjectRead)
def archive_project(
    project_id: uuid.UUID, request: Request, db: DbSession, actor: CurrentUser
) -> ProjectRead:
    with _domain_errors():
        return service.archive_project(db, actor, project_id, ip=client_ip(request))


@router.get("/projects/{project_id}/members", response_model=list[MemberRead])
def read_members(project_id: uuid.UUID, db: DbSession, viewer: CurrentUser) -> list[MemberRead]:
    with _domain_errors():
        return service.list_members(db, viewer, project_id)


@router.post(
    "/projects/{project_id}/members",
    response_model=list[MemberRead],
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    project_id: uuid.UUID, data: MemberCreate, db: DbSession, actor: CurrentUser
) -> list[MemberRead]:
    with _domain_errors():
        return service.add_member(db, actor, project_id, data)


@router.delete("/projects/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    project_id: uuid.UUID, user_id: uuid.UUID, db: DbSession, actor: CurrentUser
) -> None:
    with _domain_errors():
        service.remove_member(db, actor, project_id, user_id)


@router.get("/coordinator/review-queue", response_model=list[ProjectCard])
def read_review_queue(
    db: DbSession,
    reviewer: Annotated[User, Depends(require_permission(Permission.PROJECT_REVIEW))],
) -> list[ProjectCard]:
    return service.review_queue(db, reviewer)
