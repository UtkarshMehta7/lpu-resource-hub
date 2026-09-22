"""Collaboration request endpoints, mounted under /api/v1.

404 for anyone who isn't a party (or an uncontactable recipient), 403 when
a party tries the other side's action, 409 when the request is no longer
pending or a pending one already exists, 429 when sending too fast.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import enforce_collaboration_rate_limit
from app.db.session import get_db
from app.modules.collaborations import service
from app.modules.collaborations.models import CollaborationStatus
from app.modules.collaborations.policies import InvalidTransitionError, WrongPartyError
from app.modules.collaborations.schemas import Box, CollaborationCreate, CollaborationRead
from app.modules.users.models import User

router = APIRouter(tags=["collaborations"])

CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]

_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    service.CollaborationNotFoundError: (status.HTTP_404_NOT_FOUND, "Request not found."),
    service.RecipientNotFoundError: (status.HTTP_404_NOT_FOUND, "Recipient not found."),
    service.ProjectNotFoundError: (status.HTTP_404_NOT_FOUND, "Project not found."),
    WrongPartyError: (
        status.HTTP_403_FORBIDDEN,
        "Only the recipient can answer; only the sender can cancel.",
    ),
    InvalidTransitionError: (status.HTTP_409_CONFLICT, "This request is no longer pending."),
    service.DuplicatePendingError: (
        status.HTTP_409_CONFLICT,
        "You already have a pending request to this person about this.",
    ),
    service.SelfRequestError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "You can't send a request to yourself.",
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
    "/collaborations", response_model=CollaborationRead, status_code=status.HTTP_201_CREATED
)
def send_collaboration_request(
    data: CollaborationCreate,
    request: Request,
    db: DbSession,
    sender: Annotated[User, Depends(require_permission(Permission.COLLABORATION_SEND))],
) -> CollaborationRead:
    enforce_collaboration_rate_limit(request, sender.id)
    with _domain_errors():
        return service.send_request(db, sender, data)


@router.get("/me/collaborations", response_model=list[CollaborationRead])
def read_my_collaborations(
    db: DbSession,
    viewer: CurrentUser,
    box: Box = Box.INBOX,
    status_filter: Annotated[CollaborationStatus | None, Query(alias="status")] = None,
) -> list[CollaborationRead]:
    return service.list_requests(db, viewer, box, status_filter)


@router.get("/collaborations/{request_id}", response_model=CollaborationRead)
def read_collaboration(
    request_id: uuid.UUID, db: DbSession, viewer: CurrentUser
) -> CollaborationRead:
    with _domain_errors():
        return service.get_request(db, viewer, request_id)


def _respond(
    db: Session, actor: User, request_id: uuid.UUID, target: CollaborationStatus
) -> CollaborationRead:
    with _domain_errors():
        return service.respond(db, actor, request_id, target)


@router.post("/collaborations/{request_id}/accept", response_model=CollaborationRead)
def accept_collaboration(
    request_id: uuid.UUID, db: DbSession, actor: CurrentUser
) -> CollaborationRead:
    return _respond(db, actor, request_id, CollaborationStatus.ACCEPTED)


@router.post("/collaborations/{request_id}/decline", response_model=CollaborationRead)
def decline_collaboration(
    request_id: uuid.UUID, db: DbSession, actor: CurrentUser
) -> CollaborationRead:
    return _respond(db, actor, request_id, CollaborationStatus.DECLINED)


@router.post("/collaborations/{request_id}/cancel", response_model=CollaborationRead)
def cancel_collaboration(
    request_id: uuid.UUID, db: DbSession, actor: CurrentUser
) -> CollaborationRead:
    return _respond(db, actor, request_id, CollaborationStatus.CANCELLED)
