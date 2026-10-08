"""Patent endpoints, mounted under /api/v1.

Readable by every signed-in user. Recordable by students, faculty,
coordinators and administrators -- not by a dean or a facility custodian,
whose roles are deliberately read-only and deliberately narrow (ADR 0028).
Either may still be *named* as an inventor by whoever records the patent, so
nobody is cut out of the credit.

`/patent-review-queue` gets its own top-level path rather than hanging off
`/patents/...`: `/patents/{patent_id}` is registered here and FastAPI matches
in registration order, so a nested form would be swallowed and "review-queue"
parsed as a UUID. The same trap `/publication-duplicates` was moved out of.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.deps import get_current_user
from app.core.pagination import Page, PageParams
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import client_ip, enforce_search_rate_limit
from app.db.session import get_db
from app.modules.patents import priorart, service
from app.modules.patents.models import PatentStatus
from app.modules.patents.policies import InvalidTransitionError, NotAllowedActorError
from app.modules.patents.schemas import (
    PatentCreate,
    PatentDecision,
    PatentRead,
    PatentTransition,
    PatentUpdate,
    PriorArtQuery,
    PriorArtResult,
)
from app.modules.profiles.models import VerificationStatus
from app.modules.users.models import User

router = APIRouter(tags=["patents"])

CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Inventor = Annotated[User, Depends(require_permission(Permission.PATENT_CREATE))]
Reviewer = Annotated[User, Depends(require_permission(Permission.PATENT_VERIFY))]

_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    service.PatentNotFoundError: (status.HTTP_404_NOT_FOUND, "Patent not found."),
    service.NotCreatorError: (
        status.HTTP_403_FORBIDDEN,
        "Only the person who recorded this patent can change it.",
    ),
    service.DuplicateNumberError: (
        status.HTTP_409_CONFLICT,
        "A patent in this jurisdiction already carries that number.",
    ),
    service.UnknownInventorError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "One or more inventors do not name an active user.",
    ),
    service.ProjectLinkError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "You can only link patents to projects you own or belong to.",
    ),
    service.MissingTransitionDateError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Say the date the office issued it: that status cannot exist without one.",
    ),
    service.MissingDecisionNoteError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Say why. Declining without a reason is what stops the next person disclosing.",
    ),
    NotAllowedActorError: (
        status.HTTP_403_FORBIDDEN,
        "That step is not yours to take on this record.",
    ),
    service.OutOfScopeError: (
        status.HTTP_403_FORBIDDEN,
        "You can only decide records from your own department.",
    ),
    service.AlreadyDecidedError: (
        status.HTTP_409_CONFLICT,
        "This record has already been decided.",
    ),
    InvalidTransitionError: (
        status.HTTP_409_CONFLICT,
        "That is not a move the process allows from its current state.",
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
    "/patents",
    response_model=Page[PatentRead],
    dependencies=[Depends(enforce_search_rate_limit)],
)
def read_patents(
    db: DbSession,
    viewer: CurrentUser,
    params: Annotated[PageParams, Depends()],
    q: str | None = None,
    inventor_id: uuid.UUID | None = None,
    patent_status: Annotated[
        PatentStatus | None, Query(alias="status", description="Defaults to every state.")
    ] = None,
    verification_status: VerificationStatus | None = None,
    jurisdiction: str | None = None,
) -> Page[PatentRead]:
    return service.list_patents(
        db,
        viewer,
        params,
        q=q,
        inventor_id=inventor_id,
        status=patent_status,
        verification_status=verification_status,
        jurisdiction=jurisdiction,
    )


@router.post("/patents", response_model=PatentRead, status_code=status.HTTP_201_CREATED)
def create_patent(data: PatentCreate, db: DbSession, creator: Inventor) -> PatentRead:
    """Record a patent. It waits for a coordinator unless an admin entered it.

    No semantic-search embedding yet: `EntityType` has no PATENT member, and
    adding one means an enum migration plus a document builder in the search
    module. Patents are full-text searchable through their own listing in the
    meantime, and half-wiring it would have been worse than not wiring it.
    """
    with _domain_errors():
        return service.create_patent(db, creator, data)


@router.post("/patents/prior-art", response_model=PriorArtResult)
def search_prior_art(
    data: PriorArtQuery,
    db: DbSession,
    settings: AppSettings,
    actor: Inventor,
    exclude_id: uuid.UUID | None = None,
) -> PriorArtResult:
    """What is already out there that looks like this.

    A POST because the abstract is far too long for a query string, not
    because anything is stored: nothing is written, and running it twice
    costs nothing but two requests to two open indexes.
    """
    return priorart.search(
        db, settings, title=data.title, abstract=data.abstract, exclude_id=exclude_id
    )


@router.get("/patent-review-queue", response_model=list[PatentRead])
def read_review_queue(db: DbSession, reviewer: Reviewer) -> list[PatentRead]:
    """Records waiting on this reviewer: disclosures to assess, records to check."""
    return service.review_queue(db, reviewer)


@router.get("/patents/{patent_id}", response_model=PatentRead)
def read_patent(patent_id: uuid.UUID, db: DbSession, viewer: CurrentUser) -> PatentRead:
    with _domain_errors():
        return service.get_patent(db, viewer, patent_id)


@router.patch("/patents/{patent_id}", response_model=PatentRead)
def update_patent(
    patent_id: uuid.UUID, data: PatentUpdate, db: DbSession, actor: CurrentUser
) -> PatentRead:
    with _domain_errors():
        return service.update_patent(db, actor, patent_id, data)


@router.post("/patents/{patent_id}/status", response_model=PatentRead)
def move_patent_status(
    patent_id: uuid.UUID, data: PatentTransition, db: DbSession, actor: CurrentUser
) -> PatentRead:
    with _domain_errors():
        return service.move_status(db, actor, patent_id, data)


@router.post("/patents/{patent_id}/decision", response_model=PatentRead)
def decide_patent(
    patent_id: uuid.UUID,
    data: PatentDecision,
    request: Request,
    db: DbSession,
    reviewer: Reviewer,
) -> PatentRead:
    with _domain_errors():
        return service.decide(db, reviewer, patent_id, data, ip=client_ip(request))


@router.delete("/patents/{patent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_patent(
    patent_id: uuid.UUID, request: Request, db: DbSession, actor: CurrentUser
) -> None:
    with _domain_errors():
        service.delete_patent(db, actor, patent_id, ip=client_ip(request))
