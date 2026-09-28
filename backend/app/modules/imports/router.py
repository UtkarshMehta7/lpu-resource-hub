"""Profile import endpoints, mounted under /api/v1.

Three routes, all scoped to the caller's own profile. There is deliberately
no endpoint that imports into somebody else's profile: a researcher's
publication list is theirs to assert, and an administrator doing it on their
behalf would put claims in their name that they never made.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rate_limit import enforce_import_rate_limit
from app.db.session import get_db
from app.modules.imports import service
from app.modules.imports.connectors.base import ProfileQuery
from app.modules.imports.models import ProfileImport
from app.modules.imports.schemas import (
    ImportApplyRequest,
    ImportHistoryRead,
    ImportLookupRequest,
    ImportPreviewRead,
    ImportResultRead,
)
from app.modules.users.models import User

router = APIRouter(tags=["profile import"])

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    service.ImportDisabledError: (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Profile import is switched off for this deployment.",
    ),
    service.NoProfileError: (
        status.HTTP_409_CONFLICT,
        "Set up your researcher profile before importing into it.",
    ),
    service.NothingFoundError: (
        status.HTTP_404_NOT_FOUND,
        "None of the sources had a record matching that. Check the ORCID iD or try a name.",
    ),
    service.OrcidTakenError: (
        status.HTTP_409_CONFLICT,
        "Another account has already claimed that ORCID iD.",
    ),
}


def _translate(exc: Exception) -> HTTPException:
    for error_type, (code, message) in _ERROR_MAP.items():
        if isinstance(exc, error_type):
            return HTTPException(status_code=code, detail=message)
    raise exc


def _query_from(payload: ImportLookupRequest) -> ProfileQuery:
    """Turn the request into a validated lookup, or a 422 explaining why not."""
    if not payload.orcid and not payload.name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Give an ORCID iD or a name to look up.",
        )
    try:
        return service.build_query(payload.orcid, payload.name, payload.affiliation)
    except service.InvalidOrcidError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That does not look like an ORCID iD. They look like 0000-0002-1825-0097.",
        ) from exc


@router.post("/me/profile/import/preview", response_model=ImportPreviewRead)
def preview_import(
    request: Request,
    payload: ImportLookupRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> ImportPreviewRead:
    """Read the external sources and report what would be imported.

    Writes nothing. Safe to call repeatedly, subject to the rate limit.
    """
    enforce_import_rate_limit(request, current_user.id)
    query = _query_from(payload)
    try:
        result = service.preview(db, current_user, query)
    except Exception as exc:  # noqa: BLE001 - mapped to HTTP below, re-raised if unknown
        raise _translate(exc) from exc
    return ImportPreviewRead.model_validate(result)


@router.post("/me/profile/import", response_model=ImportResultRead)
def apply_import(
    request: Request,
    payload: ImportApplyRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> ImportResultRead:
    """Import the fields and publications the researcher ticked.

    The sources are read again rather than trusting the payload, so nothing
    bibliographic ever comes from the browser.
    """
    enforce_import_rate_limit(request, current_user.id)
    query = _query_from(payload)
    try:
        result = service.apply(
            db, current_user, query, fields=payload.fields, work_keys=payload.work_keys
        )
    except Exception as exc:  # noqa: BLE001 - mapped to HTTP below, re-raised if unknown
        raise _translate(exc) from exc
    return ImportResultRead.model_validate(result)


@router.get("/me/profile/import/history", response_model=list[ImportHistoryRead])
def import_history(db: DbSession, current_user: CurrentUser) -> list[ImportHistoryRead]:
    """The caller's own past imports, newest first."""
    rows = db.scalars(
        select(ProfileImport)
        .where(ProfileImport.user_id == current_user.id)
        .order_by(ProfileImport.created_at.desc())
        .limit(20)
    ).all()
    return [ImportHistoryRead.model_validate(row) for row in rows]


__all__ = ["router"]
