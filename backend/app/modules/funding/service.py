"""Funding calls: browse, and manage as coordinator/admin.

Funding calls are public to every signed-in user. Nothing here invents a real
call: seeded rows are flagged `is_demo` and the UI says so.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams
from app.modules.funding.models import FundingOpportunity, FundingResearchArea, FundingStatus
from app.modules.funding.schemas import FundingCreate, FundingRead, FundingUpdate
from app.modules.taxonomy.models import ResearchArea
from app.modules.users.models import User


class FundingNotFoundError(Exception):
    """No such funding call."""


class UnknownResearchAreaError(Exception):
    """One or more research area ids don't exist."""


def _areas_by_funding(db: Session, funding_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    result: dict[uuid.UUID, list[str]] = {}
    if not funding_ids:
        return result
    for funding_id, name in db.execute(
        select(FundingResearchArea.funding_id, ResearchArea.name)
        .join(ResearchArea, ResearchArea.id == FundingResearchArea.research_area_id)
        .where(FundingResearchArea.funding_id.in_(funding_ids))
        .order_by(ResearchArea.name)
    ).all():
        result.setdefault(funding_id, []).append(name)
    return result


def funding_reads(db: Session, rows: Sequence[FundingOpportunity]) -> list[FundingRead]:
    """Read models for specific rows; shared with saved items (Step 12)."""
    areas = _areas_by_funding(db, [row.id for row in rows])
    return [
        FundingRead(
            id=row.id,
            organization=row.organization,
            title=row.title,
            description=row.description,
            eligibility=row.eligibility,
            amount_text=row.amount_text,
            amount_min=row.amount_min,
            amount_max=row.amount_max,
            deadline=row.deadline,
            official_source_url=row.official_source_url,
            status=row.status,
            is_demo=row.is_demo,
            research_areas=areas.get(row.id, []),
            created_at=row.created_at,
        )
        for row in rows
    ]


def _validate_areas(db: Session, area_ids: Sequence[uuid.UUID]) -> None:
    if not area_ids:
        return
    found = set(
        db.execute(select(ResearchArea.id).where(ResearchArea.id.in_(set(area_ids)))).scalars()
    )
    if set(area_ids) - found:
        raise UnknownResearchAreaError


def _replace_areas(db: Session, funding_id: uuid.UUID, area_ids: Sequence[uuid.UUID]) -> None:
    db.execute(delete(FundingResearchArea).where(FundingResearchArea.funding_id == funding_id))
    db.add_all(
        FundingResearchArea(funding_id=funding_id, research_area_id=area_id)
        for area_id in set(area_ids)
    )


def load_funding(db: Session, funding_id: uuid.UUID) -> FundingOpportunity:
    funding = db.get(FundingOpportunity, funding_id)
    if funding is None:
        raise FundingNotFoundError
    return funding


def get_funding(db: Session, funding_id: uuid.UUID) -> FundingRead:
    return funding_reads(db, [load_funding(db, funding_id)])[0]


def list_funding(
    db: Session,
    params: PageParams,
    *,
    q: str | None = None,
    status: FundingStatus | None = None,
    research_area_id: uuid.UUID | None = None,
    deadline_before: date | None = None,
    open_only: bool = False,
) -> Page[FundingRead]:
    query = select(FundingOpportunity)
    tsquery = func.websearch_to_tsquery("english", q) if q else None
    if tsquery is not None:
        query = query.where(FundingOpportunity.search_document.op("@@")(tsquery))
    if status is not None:
        query = query.where(FundingOpportunity.status == status)
    if open_only:
        query = query.where(
            FundingOpportunity.status == FundingStatus.OPEN,
            FundingOpportunity.deadline >= datetime.now(UTC).date(),
        )
    if research_area_id is not None:
        area_ids = select(ResearchArea.id).where(
            (ResearchArea.id == research_area_id) | (ResearchArea.parent_id == research_area_id)
        )
        query = query.where(
            FundingOpportunity.id.in_(
                select(FundingResearchArea.funding_id).where(
                    FundingResearchArea.research_area_id.in_(area_ids)
                )
            )
        )
    if deadline_before is not None:
        query = query.where(FundingOpportunity.deadline <= deadline_before)

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    if tsquery is not None:
        query = query.order_by(func.ts_rank(FundingOpportunity.search_document, tsquery).desc())
    query = query.order_by(FundingOpportunity.deadline, FundingOpportunity.title)
    rows = db.execute(query.offset(params.offset).limit(params.page_size)).scalars().all()
    return Page[FundingRead](
        items=funding_reads(db, list(rows)),
        page=params.page,
        page_size=params.page_size,
        total=total,
    )


def create_funding(
    db: Session, actor: User, data: FundingCreate, *, is_demo: bool = False
) -> FundingRead:
    _validate_areas(db, data.research_area_ids)
    funding = FundingOpportunity(
        organization=data.organization,
        title=data.title,
        description=data.description,
        eligibility=data.eligibility,
        amount_text=data.amount_text,
        amount_min=data.amount_min,
        amount_max=data.amount_max,
        deadline=data.deadline,
        official_source_url=data.official_source_url,
        is_demo=is_demo,
        created_by=actor.id,
    )
    db.add(funding)
    db.flush()
    _replace_areas(db, funding.id, data.research_area_ids)
    db.commit()
    db.refresh(funding)
    return funding_reads(db, [funding])[0]


def update_funding(db: Session, funding_id: uuid.UUID, data: FundingUpdate) -> FundingRead:
    funding = load_funding(db, funding_id)
    if data.research_area_ids is not None:
        _validate_areas(db, data.research_area_ids)
    for field in ("organization", "title", "description", "deadline", "status"):
        value = getattr(data, field)
        if value is not None:
            setattr(funding, field, value)
    for field in ("eligibility", "amount_text", "amount_min", "amount_max", "official_source_url"):
        if field in data.model_fields_set:
            setattr(funding, field, getattr(data, field))
    if data.research_area_ids is not None:
        _replace_areas(db, funding.id, data.research_area_ids)
    db.commit()
    db.refresh(funding)
    return funding_reads(db, [funding])[0]


def delete_funding(db: Session, funding_id: uuid.UUID) -> None:
    db.delete(load_funding(db, funding_id))
    db.commit()
