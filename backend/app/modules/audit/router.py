"""Audit log read endpoint, mounted under /api/v1/admin."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams
from app.core.permissions import Permission, require_permission
from app.db.session import get_db
from app.modules.audit.schemas import AuditLogRead
from app.modules.audit.service import list_logs

router = APIRouter(tags=["audit"])


@router.get(
    "/audit-logs",
    response_model=Page[AuditLogRead],
    dependencies=[Depends(require_permission(Permission.AUDIT_READ))],
)
def read_audit_logs(
    db: Annotated[Session, Depends(get_db)],
    params: Annotated[PageParams, Depends()],
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
) -> Page[AuditLogRead]:
    return list_logs(
        db,
        params,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        action=action,
    )
