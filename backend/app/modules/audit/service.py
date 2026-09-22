"""Append-only audit log: write and query. Services never import FastAPI."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams
from app.modules.audit.models import AuditLog
from app.modules.audit.schemas import AuditLogRead


def record(
    db: Session,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Inserts one audit row. Never updated or deleted afterwards."""
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            after=after,
            ip=ip,
        )
    )


def list_logs(
    db: Session,
    params: PageParams,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
) -> Page[AuditLogRead]:
    query = select(AuditLog)
    if entity_type is not None:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(AuditLog.entity_id == entity_id)
    if actor_id is not None:
        query = query.where(AuditLog.actor_id == actor_id)
    if action is not None:
        query = query.where(AuditLog.action == action)

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = (
        db.execute(
            query.order_by(AuditLog.created_at.desc()).offset(params.offset).limit(params.page_size)
        )
        .scalars()
        .all()
    )
    return Page[AuditLogRead](
        items=[AuditLogRead.model_validate(row) for row in rows],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )
