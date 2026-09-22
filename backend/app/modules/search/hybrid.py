"""Natural-language search: lexical + semantic, fused.

For each entity type the same query runs twice -- PostgreSQL full-text search
(precise on the words that actually appear) and pgvector nearest neighbours
(forgiving about vocabulary) -- and the two rankings are merged with
reciprocal rank fusion. RRF needs no score calibration between a `ts_rank`
and a cosine distance, which is exactly the problem with mixing them directly.

The query is embedded once and the visibility of semantic hits is checked
with one targeted query per type, so the extra cost over lexical search is
one model call plus four indexed lookups.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.pagination import PageParams
from app.ml.embeddings import embed_text
from app.modules.opportunities.models import Opportunity
from app.modules.opportunities.policies import visibility_filter as opportunity_visibility
from app.modules.opportunities.schemas import OpportunityCard
from app.modules.opportunities.service import list_opportunities, opportunity_cards
from app.modules.projects.models import Project
from app.modules.projects.policies import visibility_filter as project_visibility
from app.modules.projects.schemas import ProjectCard
from app.modules.projects.service import list_projects, project_cards
from app.modules.publications.models import Publication
from app.modules.publications.schemas import PublicationRead
from app.modules.publications.service import get_publication, list_publications
from app.modules.researchers.directory import cards_for_researchers, list_researchers
from app.modules.researchers.search_schemas import ResearcherCard
from app.modules.search.models import EntityType
from app.modules.search.service import (
    MIN_SIMILARITY,
    reciprocal_rank_fusion,
    vector_neighbours,
)
from app.modules.users.models import User

# How many lexical hits to fuse with the semantic ones.
LEXICAL_DEPTH = 50


def _visible_semantic_ids(
    db: Session, viewer: User, entity_type: EntityType, candidates: Sequence[uuid.UUID]
) -> list[uuid.UUID]:
    """Filters semantic hits down to what this viewer may see, in order.

    The same visibility rules the list endpoints use -- a semantic hit on a
    draft project or an unpublished opening is dropped here, so embeddings
    can never widen what is discoverable.
    """
    if not candidates:
        return []
    if entity_type is EntityType.PROJECT:
        allowed = set(
            db.execute(
                select(Project.id).where(
                    Project.id.in_(candidates),
                    Project.deleted_at.is_(None),
                    project_visibility(viewer),
                )
            ).scalars()
        )
    elif entity_type is EntityType.OPPORTUNITY:
        allowed = set(
            db.execute(
                select(Opportunity.id).where(
                    Opportunity.id.in_(candidates), opportunity_visibility(viewer)
                )
            ).scalars()
        )
    elif entity_type is EntityType.PUBLICATION:
        # Publications are readable by every signed-in user.
        allowed = set(
            db.execute(select(Publication.id).where(Publication.id.in_(candidates))).scalars()
        )
    else:
        allowed = {card.user_id for card in cards_for_researchers(db, list(candidates))}
    return [entity_id for entity_id in candidates if entity_id in allowed]


def hybrid_search(
    db: Session, viewer: User, query: str, limit: int = 10
) -> tuple[
    list[ResearcherCard], list[ProjectCard], list[PublicationRead], list[OpportunityCard], bool
]:
    """Returns cards per type, plus whether the semantic half actually ran."""
    params = PageParams(page=1, page_size=LEXICAL_DEPTH)
    researchers = list_researchers(db, params, q=query).items
    projects = list_projects(db, viewer, params, q=query).items
    publications = list_publications(db, viewer, params, q=query).items
    opportunities = list_opportunities(db, viewer, params, q=query).items

    # One model call for the whole search, not one per entity type.
    query_vector = embed_text(query)
    if query_vector is None:
        return (
            researchers[:limit],
            projects[:limit],
            publications[:limit],
            opportunities[:limit],
            False,
        )

    def fused(entity_type: EntityType, lexical_ids: Sequence[uuid.UUID]) -> list[uuid.UUID]:
        neighbours = [
            entity_id
            for entity_id, similarity in vector_neighbours(db, query_vector, entity_type)
            if similarity >= MIN_SIMILARITY
        ]
        visible = _visible_semantic_ids(db, viewer, entity_type, neighbours)
        return reciprocal_rank_fusion([list(lexical_ids), visible])[:limit]

    researcher_ids = fused(EntityType.RESEARCHER, [card.user_id for card in researchers])
    project_ids = fused(EntityType.PROJECT, [card.id for card in projects])
    publication_ids = fused(EntityType.PUBLICATION, [item.id for item in publications])
    opportunity_ids = fused(EntityType.OPPORTUNITY, [card.id for card in opportunities])

    return (
        _ordered(cards_for_researchers(db, researcher_ids), researcher_ids, "user_id"),
        _ordered(project_cards(db, _projects_by_id(db, project_ids)), project_ids, "id"),
        [get_publication(db, viewer, publication_id) for publication_id in publication_ids],
        _ordered(
            opportunity_cards(db, viewer, _opportunities_by_id(db, opportunity_ids)),
            opportunity_ids,
            "id",
        ),
        True,
    )


def _ordered[CardT](cards: Sequence[CardT], order: Sequence[uuid.UUID], key: str) -> list[CardT]:
    """Card builders don't preserve the fused order, so restore it here."""
    by_id = {getattr(card, key): card for card in cards}
    return [by_id[entity_id] for entity_id in order if entity_id in by_id]


def _projects_by_id(db: Session, ids: Sequence[uuid.UUID]) -> list[Project]:
    if not ids:
        return []
    return list(db.execute(select(Project).where(Project.id.in_(ids))).scalars())


def _opportunities_by_id(db: Session, ids: Sequence[uuid.UUID]) -> list[Opportunity]:
    if not ids:
        return []
    return list(db.execute(select(Opportunity).where(Opportunity.id.in_(ids))).scalars())
