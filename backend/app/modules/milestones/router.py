"""Milestone endpoints, mounted under /api/v1.

Milestones hang off a project for creation and listing, and are addressed
directly once they exist -- the same shape the applications and bookings
modules already use.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import Permission, require_permission
from app.db.session import get_db
from app.modules.milestones import service
from app.modules.milestones.policies import (
    CrossProjectDependencyError,
    DependencyCycleError,
    InvalidTransitionError,
    NotOwnerError,
    ProjectNotEditableError,
)
from app.modules.milestones.schemas import (
    AtRiskProject,
    DependencyCreate,
    MilestoneCreate,
    MilestoneRead,
    MilestoneUpdate,
    MyMilestone,
    StatusChangeRequest,
)
from app.modules.projects.service import ProjectNotFoundError
from app.modules.users.models import User

router = APIRouter(tags=["milestones"])

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    # Both are 404 on purpose: a caller who cannot see the project must not
    # learn that a milestone on it exists.
    service.MilestoneNotFoundError: (status.HTTP_404_NOT_FOUND, "Milestone not found."),
    ProjectNotFoundError: (status.HTTP_404_NOT_FOUND, "Project not found."),
    NotOwnerError: (
        status.HTTP_403_FORBIDDEN,
        "Only the project owner can change the milestone plan.",
    ),
    ProjectNotEditableError: (
        status.HTTP_409_CONFLICT,
        "Milestones can only change while a project is a draft or active.",
    ),
    InvalidTransitionError: (
        status.HTTP_409_CONFLICT,
        "That is not a move this milestone can make from where it is.",
    ),
    DependencyCycleError: (
        status.HTTP_409_CONFLICT,
        "That would make the milestone wait on itself.",
    ),
    CrossProjectDependencyError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "A milestone can only wait on another milestone of the same project.",
    ),
    service.TooManyMilestonesError: (
        status.HTTP_409_CONFLICT,
        f"A project can have at most {service.MAX_MILESTONES_PER_PROJECT} milestones.",
    ),
}


def _translate(exc: Exception) -> HTTPException:
    for error_type, (code, message) in _ERROR_MAP.items():
        if isinstance(exc, error_type):
            return HTTPException(status_code=code, detail=message)
    raise exc


@router.get("/projects/{project_id}/milestones", response_model=list[MilestoneRead])
def list_project_milestones(
    project_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> list[MilestoneRead]:
    """Every milestone of a project the caller can see, in plan order."""
    try:
        return service.list_milestones(db, current_user, project_id)
    except Exception as exc:  # noqa: BLE001 - mapped to HTTP below, re-raised if unknown
        raise _translate(exc) from exc


@router.post(
    "/projects/{project_id}/milestones",
    response_model=MilestoneRead,
    status_code=status.HTTP_201_CREATED,
)
def create_milestone(
    project_id: uuid.UUID, payload: MilestoneCreate, db: DbSession, current_user: CurrentUser
) -> MilestoneRead:
    try:
        return service.create_milestone(db, current_user, project_id, payload)
    except Exception as exc:  # noqa: BLE001 - mapped to HTTP below, re-raised if unknown
        raise _translate(exc) from exc


@router.get("/milestones/{milestone_id}", response_model=MilestoneRead)
def read_milestone(
    milestone_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> MilestoneRead:
    try:
        return service.get_milestone(db, current_user, milestone_id)
    except Exception as exc:  # noqa: BLE001 - mapped to HTTP below, re-raised if unknown
        raise _translate(exc) from exc


@router.patch("/milestones/{milestone_id}", response_model=MilestoneRead)
def update_milestone(
    milestone_id: uuid.UUID, payload: MilestoneUpdate, db: DbSession, current_user: CurrentUser
) -> MilestoneRead:
    try:
        return service.update_milestone(db, current_user, milestone_id, payload)
    except Exception as exc:  # noqa: BLE001 - mapped to HTTP below, re-raised if unknown
        raise _translate(exc) from exc


@router.delete("/milestones/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_milestone(
    milestone_id: uuid.UUID, request: Request, db: DbSession, current_user: CurrentUser
) -> None:
    try:
        service.delete_milestone(
            db, current_user, milestone_id, ip=request.client.host if request.client else None
        )
    except Exception as exc:  # noqa: BLE001 - mapped to HTTP below, re-raised if unknown
        raise _translate(exc) from exc


@router.post("/milestones/{milestone_id}/status", response_model=MilestoneRead)
def change_milestone_status(
    milestone_id: uuid.UUID,
    payload: StatusChangeRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> MilestoneRead:
    """Move a milestone along. Team members may; onlookers may not."""
    try:
        return service.change_status(db, current_user, milestone_id, payload.status)
    except Exception as exc:  # noqa: BLE001 - mapped to HTTP below, re-raised if unknown
        raise _translate(exc) from exc


@router.post("/milestones/{milestone_id}/dependencies", response_model=MilestoneRead)
def add_milestone_dependency(
    milestone_id: uuid.UUID, payload: DependencyCreate, db: DbSession, current_user: CurrentUser
) -> MilestoneRead:
    try:
        return service.add_dependency(db, current_user, milestone_id, payload.depends_on_id)
    except Exception as exc:  # noqa: BLE001 - mapped to HTTP below, re-raised if unknown
        raise _translate(exc) from exc


@router.delete(
    "/milestones/{milestone_id}/dependencies/{depends_on_id}", response_model=MilestoneRead
)
def remove_milestone_dependency(
    milestone_id: uuid.UUID,
    depends_on_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> MilestoneRead:
    try:
        return service.remove_dependency(db, current_user, milestone_id, depends_on_id)
    except Exception as exc:  # noqa: BLE001 - mapped to HTTP below, re-raised if unknown
        raise _translate(exc) from exc


@router.get("/me/milestones", response_model=list[MyMilestone])
def my_milestones(db: DbSession, current_user: CurrentUser) -> list[MyMilestone]:
    """What the caller owes, across every project, soonest first."""
    return service.my_milestones(db, current_user)


@router.get("/coordinator/at-risk-projects", response_model=list[AtRiskProject])
def at_risk_projects(
    db: DbSession,
    viewer: Annotated[User, Depends(require_permission(Permission.PROJECT_REVIEW))],
) -> list[AtRiskProject]:
    """Projects with slipping milestones, most overdue first.

    Scoped like every other project query: a coordinator sees their
    department, an administrator sees everything.
    """
    return service.at_risk_projects(db, viewer)


__all__ = ["router"]
