"""Duplicate review endpoints, mounted under /api/v1.

Its own resource path, `/publication-duplicates`, rather than
`/publications/duplicates`: the publications router registers
`/publications/{publication_id}` and FastAPI matches in registration order,
so the nested form was swallowed by it and "duplicates" was parsed as a UUID.
Mounting this router first would also have worked, and would have broken
silently the day somebody reordered `app/main.py`.

A review row is not a publication anyway -- it is a judgement about two of
them -- so it deserves its own path.

Finding duplicates is a scan a person runs, not something on a request path:
it is O(n^2) over stored publications by design (see detect.py), and a
reviewer wants a stable list to work down rather than one that shifts under
them.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import client_ip
from app.db.session import get_db
from app.modules.deduplication import service
from app.modules.deduplication.models import DuplicateStatus
from app.modules.deduplication.policies import InvalidTransitionError
from app.modules.deduplication.schemas import (
    DuplicateDecision,
    DuplicateRead,
    ScanResult,
)
from app.modules.users.models import User

router = APIRouter(tags=["deduplication"])

DbSession = Annotated[Session, Depends(get_db)]
Curator = Annotated[User, Depends(require_permission(Permission.PUBLICATION_DEDUPLICATE))]

_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    service.DuplicateNotFoundError: (status.HTTP_404_NOT_FOUND, "No such duplicate review."),
    service.KeepIdRequiredError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Say which record to keep: merging has to choose a survivor.",
    ),
    service.KeepIdNotInPairError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "The record to keep must be one of the two under review.",
    ),
    service.PairIncompleteError: (
        status.HTTP_409_CONFLICT,
        "One of these records no longer exists, so there is nothing to merge.",
    ),
    service.NothingToUndoError: (
        status.HTTP_409_CONFLICT,
        "Only a merge can be undone, and only while its snapshot is intact.",
    ),
    InvalidTransitionError: (
        status.HTTP_409_CONFLICT,
        "That is not a move this review allows from its current state.",
    ),
}


@contextmanager
def _domain_errors() -> Iterator[None]:
    try:
        yield
    except tuple(_ERROR_MAP) as exc:
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from exc


@router.post("/publication-duplicates/scan", response_model=ScanResult)
def scan_for_duplicates(request: Request, db: DbSession, curator: Curator) -> ScanResult:
    """Look for suspected duplicates and queue the new ones.

    Idempotent, and never resurrects a pair somebody has already judged.
    """
    return service.scan(db, curator, ip=client_ip(request))


@router.get("/publication-duplicates", response_model=Page[DuplicateRead])
def read_duplicates(
    db: DbSession,
    curator: Curator,
    params: Annotated[PageParams, Depends()],
    duplicate_status: Annotated[
        DuplicateStatus | None,
        Query(alias="status", description="Defaults to every state."),
    ] = None,
) -> Page[DuplicateRead]:
    """The queue, strongest match first."""
    return service.list_duplicates(db, params, status=duplicate_status)


@router.get("/publication-duplicates/{duplicate_id}", response_model=DuplicateRead)
def read_duplicate(duplicate_id: uuid.UUID, db: DbSession, curator: Curator) -> DuplicateRead:
    with _domain_errors():
        return service.get_duplicate(db, duplicate_id)


@router.post("/publication-duplicates/{duplicate_id}/decision", response_model=DuplicateRead)
def decide_duplicate(
    duplicate_id: uuid.UUID,
    data: DuplicateDecision,
    request: Request,
    db: DbSession,
    curator: Curator,
) -> DuplicateRead:
    """Merge the pair, mark them separate, or set them aside.

    A merge carries the losing record's authors and project links onto the
    survivor, snapshots it, and deletes it. Audited under its own action.
    """
    with _domain_errors():
        return service.decide(db, curator, duplicate_id, data, ip=client_ip(request))


@router.post("/publication-duplicates/{duplicate_id}/undo", response_model=DuplicateRead)
def undo_duplicate_merge(
    duplicate_id: uuid.UUID, request: Request, db: DbSession, curator: Curator
) -> DuplicateRead:
    """Put back the record a merge removed, with its authors and links.

    The restored record gets a new id, so a link saved to the old one will not
    resolve; everything else returns.
    """
    with _domain_errors():
        return service.undo_merge(db, curator, duplicate_id, ip=client_ip(request))
