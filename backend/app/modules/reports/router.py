"""Content report endpoints, mounted under /api/v1.

Reporting something you can't see is a 404, so reports can't be used to
discover hidden content.
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
from app.core.rate_limit import client_ip
from app.db.session import get_db
from app.modules.reports import service
from app.modules.reports.models import ReportStatus
from app.modules.reports.schemas import ReportCreate, ReportRead, ReportResolve
from app.modules.users.models import User

router = APIRouter(tags=["reports"])

DbSession = Annotated[Session, Depends(get_db)]
Moderator = Annotated[User, Depends(require_permission(Permission.REPORT_MODERATE))]

_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    service.TargetNotFoundError: (status.HTTP_404_NOT_FOUND, "That content was not found."),
    service.ReportNotFoundError: (status.HTTP_404_NOT_FOUND, "Report not found."),
    service.DuplicateReportError: (
        status.HTTP_409_CONFLICT,
        "You already have an open report about this.",
    ),
    service.AlreadyResolvedError: (
        status.HTTP_409_CONFLICT,
        "This report has already been resolved.",
    ),
}


@contextmanager
def _domain_errors() -> Iterator[None]:
    try:
        yield
    except tuple(_ERROR_MAP) as exc:
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from exc


@router.post("/reports", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
def create_report(
    data: ReportCreate,
    db: DbSession,
    reporter: Annotated[User, Depends(get_current_user)],
) -> ReportRead:
    with _domain_errors():
        return service.create_report(db, reporter, data)


@router.get("/admin/reports", response_model=list[ReportRead])
def read_reports(
    db: DbSession,
    moderator: Moderator,
    status_filter: Annotated[ReportStatus | None, Query(alias="status")] = ReportStatus.OPEN,
) -> list[ReportRead]:
    return service.list_reports(db, moderator, status_filter)


@router.post("/admin/reports/{report_id}/resolve", response_model=ReportRead)
def resolve_report(
    report_id: uuid.UUID,
    data: ReportResolve,
    request: Request,
    db: DbSession,
    moderator: Moderator,
) -> ReportRead:
    with _domain_errors():
        return service.resolve_report(db, moderator, report_id, data, ip=client_ip(request))
