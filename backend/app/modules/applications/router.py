"""Application endpoints, mounted under /api/v1.

Only the opportunity's creator decides; the scoped coordinator and admins
can read. Anyone else asking for an application gets 404; asking for an
opportunity's applicant list they may see but not read gets 403.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import client_ip
from app.db.session import get_db
from app.modules.applications import service
from app.modules.applications.policies import IneligibleApplicantError, InvalidTransitionError
from app.modules.applications.schemas import (
    ApplicationCreate,
    ApplicationRead,
    StatusChangeRequest,
    WithdrawRequest,
)
from app.modules.opportunities.service import DeadlinePassedError, OpportunityNotFoundError
from app.modules.users.models import User

router = APIRouter(tags=["applications"])

CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]

_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    OpportunityNotFoundError: (status.HTTP_404_NOT_FOUND, "Opportunity not found."),
    service.ApplicationNotFoundError: (status.HTTP_404_NOT_FOUND, "Application not found."),
    service.OwnOpportunityError: (
        status.HTTP_403_FORBIDDEN,
        "You can't apply to your own opportunity.",
    ),
    IneligibleApplicantError: (
        status.HTTP_403_FORBIDDEN,
        "Students apply to student openings; faculty only to collaborations.",
    ),
    service.NotReviewerError: (
        status.HTTP_403_FORBIDDEN,
        "Only the opportunity's creator can decide applications.",
    ),
    service.NotApplicantError: (
        status.HTTP_403_FORBIDDEN,
        "Only the applicant can withdraw an application.",
    ),
    service.CannotViewApplicationsError: (
        status.HTTP_403_FORBIDDEN,
        "You can't view applications for this opportunity.",
    ),
    service.NotOpenError: (
        status.HTTP_409_CONFLICT,
        "This opportunity isn't accepting applications.",
    ),
    DeadlinePassedError: (status.HTTP_409_CONFLICT, "The deadline has passed."),
    service.DuplicateApplicationError: (
        status.HTTP_409_CONFLICT,
        "You have already applied to this opportunity.",
    ),
    service.PositionsFilledError: (
        status.HTTP_409_CONFLICT,
        "All positions for this opportunity are filled.",
    ),
    InvalidTransitionError: (
        status.HTTP_409_CONFLICT,
        "That change isn't allowed from the application's current status.",
    ),
}


@contextmanager
def _domain_errors() -> Iterator[None]:
    try:
        yield
    except tuple(_ERROR_MAP) as exc:
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from exc


@router.post(
    "/opportunities/{opportunity_id}/applications",
    response_model=ApplicationRead,
    status_code=status.HTTP_201_CREATED,
)
def apply(
    opportunity_id: uuid.UUID,
    data: ApplicationCreate,
    db: DbSession,
    applicant: Annotated[User, Depends(require_permission(Permission.APPLICATION_SUBMIT))],
) -> ApplicationRead:
    with _domain_errors():
        return service.apply(db, applicant, opportunity_id, data)


@router.get("/opportunities/{opportunity_id}/applications", response_model=list[ApplicationRead])
def read_opportunity_applications(
    opportunity_id: uuid.UUID, db: DbSession, viewer: CurrentUser
) -> list[ApplicationRead]:
    with _domain_errors():
        return service.list_for_opportunity(db, viewer, opportunity_id)


@router.get("/me/applications", response_model=list[ApplicationRead])
def read_my_applications(db: DbSession, viewer: CurrentUser) -> list[ApplicationRead]:
    return service.my_applications(db, viewer)


@router.get("/applications/{application_id}", response_model=ApplicationRead)
def read_application(
    application_id: uuid.UUID, db: DbSession, viewer: CurrentUser
) -> ApplicationRead:
    with _domain_errors():
        return service.get_application(db, viewer, application_id)


@router.post("/applications/{application_id}/status", response_model=ApplicationRead)
def change_application_status(
    application_id: uuid.UUID,
    data: StatusChangeRequest,
    request: Request,
    db: DbSession,
    reviewer: CurrentUser,
) -> ApplicationRead:
    with _domain_errors():
        return service.change_status(db, reviewer, application_id, data, ip=client_ip(request))


@router.post("/applications/{application_id}/withdraw", response_model=ApplicationRead)
def withdraw_application(
    application_id: uuid.UUID, data: WithdrawRequest, db: DbSession, applicant: CurrentUser
) -> ApplicationRead:
    with _domain_errors():
        return service.withdraw(db, applicant, application_id, data.note)
