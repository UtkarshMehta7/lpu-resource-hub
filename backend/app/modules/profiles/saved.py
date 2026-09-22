"""Saved items: a user's private bookmarks of projects, opportunities and
researchers.

A bookmark never widens visibility: items are re-checked against the usual
visibility rules when the list is read, so a project that later became
private simply stops appearing.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.funding.models import FundingOpportunity
from app.modules.funding.service import funding_reads
from app.modules.opportunities.models import Opportunity
from app.modules.opportunities.policies import visibility_filter as opportunity_visibility
from app.modules.opportunities.service import opportunity_cards
from app.modules.profiles.models import ResearcherProfile, SavedItem
from app.modules.profiles.saved_schemas import SavedCreate, SavedEntry, SavedType
from app.modules.projects.models import Project
from app.modules.projects.policies import visibility_filter as project_visibility
from app.modules.projects.service import project_cards
from app.modules.researchers.directory import cards_for_researchers
from app.modules.users.models import User


class SavedItemNotFoundError(Exception):
    """No such bookmark for this user."""


class TargetNotFoundError(Exception):
    """The thing being saved doesn't exist, or the user can't see it."""


class AlreadySavedError(Exception):
    """This user has already saved this item."""


def _assert_target_visible(db: Session, viewer: User, data: SavedCreate) -> None:
    if data.project_id is not None:
        found = db.execute(
            select(Project.id).where(
                Project.id == data.project_id,
                Project.deleted_at.is_(None),
                project_visibility(viewer),
            )
        ).scalar_one_or_none()
    elif data.opportunity_id is not None:
        found = db.execute(
            select(Opportunity.id).where(
                Opportunity.id == data.opportunity_id, opportunity_visibility(viewer)
            )
        ).scalar_one_or_none()
    elif data.funding_id is not None:
        found = db.execute(
            select(FundingOpportunity.id).where(FundingOpportunity.id == data.funding_id)
        ).scalar_one_or_none()
    else:
        found = db.execute(
            select(User.id)
            .join(ResearcherProfile, ResearcherProfile.user_id == User.id)
            .where(User.id == data.researcher_id, User.is_active.is_(True))
        ).scalar_one_or_none()
    if found is None:
        raise TargetNotFoundError


def save_item(db: Session, viewer: User, data: SavedCreate) -> SavedEntry:
    _assert_target_visible(db, viewer, data)
    item = SavedItem(
        user_id=viewer.id,
        project_id=data.project_id,
        opportunity_id=data.opportunity_id,
        researcher_id=data.researcher_id,
        funding_id=data.funding_id,
    )
    db.add(item)
    try:
        # The partial unique indexes are the real guard against duplicates.
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AlreadySavedError from exc
    db.refresh(item)
    return _to_entries(db, viewer, [item])[0]


def delete_saved_item(db: Session, viewer: User, saved_id: uuid.UUID) -> None:
    item = db.get(SavedItem, saved_id)
    if item is None or item.user_id != viewer.id:
        raise SavedItemNotFoundError
    db.delete(item)
    db.commit()


def list_saved(db: Session, viewer: User, saved_type: SavedType | None = None) -> list[SavedEntry]:
    query = select(SavedItem).where(SavedItem.user_id == viewer.id)
    if saved_type is SavedType.PROJECT:
        query = query.where(SavedItem.project_id.is_not(None))
    elif saved_type is SavedType.OPPORTUNITY:
        query = query.where(SavedItem.opportunity_id.is_not(None))
    elif saved_type is SavedType.RESEARCHER:
        query = query.where(SavedItem.researcher_id.is_not(None))
    elif saved_type is SavedType.FUNDING:
        query = query.where(SavedItem.funding_id.is_not(None))
    rows = db.execute(query.order_by(SavedItem.created_at.desc())).scalars().all()
    return _to_entries(db, viewer, list(rows))


def _to_entries(db: Session, viewer: User, items: Sequence[SavedItem]) -> list[SavedEntry]:
    if not items:
        return []
    project_ids = [i.project_id for i in items if i.project_id]
    opportunity_ids = [i.opportunity_id for i in items if i.opportunity_id]
    researcher_ids = [i.researcher_id for i in items if i.researcher_id]
    funding_ids = [i.funding_id for i in items if i.funding_id]

    projects = {
        card.id: card
        for card in project_cards(
            db,
            list(
                db.execute(
                    select(Project).where(
                        Project.id.in_(project_ids),
                        Project.deleted_at.is_(None),
                        project_visibility(viewer),
                    )
                ).scalars()
            ),
        )
    }
    opportunities = {
        card.id: card
        for card in opportunity_cards(
            db,
            viewer,
            list(
                db.execute(
                    select(Opportunity).where(
                        Opportunity.id.in_(opportunity_ids), opportunity_visibility(viewer)
                    )
                ).scalars()
            ),
        )
    }
    researchers = {card.user_id: card for card in cards_for_researchers(db, researcher_ids)}
    funding = {
        read.id: read
        for read in funding_reads(
            db,
            list(
                db.execute(
                    select(FundingOpportunity).where(FundingOpportunity.id.in_(funding_ids))
                ).scalars()
            ),
        )
    }

    entries: list[SavedEntry] = []
    for item in items:
        if item.project_id is not None and item.project_id in projects:
            entries.append(
                SavedEntry(
                    id=item.id,
                    saved_type=SavedType.PROJECT,
                    created_at=item.created_at,
                    item=projects[item.project_id],
                )
            )
        elif item.opportunity_id is not None and item.opportunity_id in opportunities:
            entries.append(
                SavedEntry(
                    id=item.id,
                    saved_type=SavedType.OPPORTUNITY,
                    created_at=item.created_at,
                    item=opportunities[item.opportunity_id],
                )
            )
        elif item.funding_id is not None and item.funding_id in funding:
            entries.append(
                SavedEntry(
                    id=item.id,
                    saved_type=SavedType.FUNDING,
                    created_at=item.created_at,
                    item=funding[item.funding_id],
                )
            )
        elif item.researcher_id is not None and item.researcher_id in researchers:
            entries.append(
                SavedEntry(
                    id=item.id,
                    saved_type=SavedType.RESEARCHER,
                    created_at=item.created_at,
                    item=researchers[item.researcher_id],
                )
            )
        # Anything no longer visible is silently skipped, never surfaced.
    return entries
