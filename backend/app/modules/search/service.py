"""Embedding pipeline and hybrid (lexical + semantic) search.

Two independent rankings are produced for a query -- PostgreSQL full-text
search and pgvector nearest neighbours -- and merged with reciprocal rank
fusion. RRF needs no score calibration between the two systems, which is
exactly the problem with mixing a `ts_rank` and a cosine distance directly.

Everything degrades cleanly: with the optional ML extra missing, embedding
is a no-op and search returns the lexical ranking alone.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.embeddings import MODEL_NAME, content_hash, embed_text, embed_texts, is_available
from app.ml.preprocessing import join_documents
from app.modules.funding.models import FundingOpportunity, FundingResearchArea
from app.modules.opportunities.models import Opportunity, OpportunitySkill
from app.modules.profiles.models import ResearcherProfile, UserResearchArea, UserSkill
from app.modules.projects.models import Project, ProjectResearchArea, ProjectSkill
from app.modules.publications.models import Publication
from app.modules.search.models import EntityEmbedding, EntityType
from app.modules.taxonomy.models import ResearchArea, Skill
from app.modules.users.models import User

logger = logging.getLogger(__name__)

# How many neighbours to pull before fusion/re-ranking.
CANDIDATE_LIMIT = 100
# Standard RRF constant: damps the influence of any single ranking's top hit.
RRF_K = 60
# Trims the long tail of near-random neighbours. Deliberately low: on short
# profile-style documents this model's cosine similarities sit around
# 0.05-0.30 even for a good match, so a high threshold would return nothing.
# It is a tail-trim, not a relevance test -- see docs/ai-evaluation.md.
MIN_SIMILARITY = 0.15


# --- what each entity's embedding is built from ------------------------------


def _tag_names(db: Session, ids: Sequence[uuid.UUID], *, skills: bool, user: bool) -> list[str]:
    if not ids:
        return []
    if user:
        model = UserSkill if skills else UserResearchArea
        join_col = UserSkill.skill_id if skills else UserResearchArea.research_area_id
        owner_col = UserSkill.user_id if skills else UserResearchArea.user_id
    else:
        model = ProjectSkill if skills else ProjectResearchArea  # type: ignore[assignment]
        join_col = ProjectSkill.skill_id if skills else ProjectResearchArea.research_area_id
        owner_col = ProjectSkill.project_id if skills else ProjectResearchArea.project_id
    target = Skill if skills else ResearchArea
    return list(
        db.execute(
            select(target.name).join(model, join_col == target.id).where(owner_col.in_(ids))
        ).scalars()
    )


def build_text(db: Session, entity_type: EntityType, entity_id: uuid.UUID) -> str | None:
    """The document an entity is embedded from, or None if it's gone."""
    if entity_type is EntityType.RESEARCHER:
        row = db.execute(
            select(User, ResearcherProfile)
            .join(ResearcherProfile, ResearcherProfile.user_id == User.id)
            .where(User.id == entity_id, User.is_active.is_(True))
        ).one_or_none()
        if row is None:
            return None
        user, profile = row
        publications = list(
            db.execute(
                select(Publication.title).where(Publication.created_by == user.id).limit(20)
            ).scalars()
        )
        return join_documents(
            [
                user.full_name,
                profile.designation,
                profile.bio,
                *_tag_names(db, [user.id], skills=True, user=True),
                *_tag_names(db, [user.id], skills=False, user=True),
                *publications,
            ]
        )

    if entity_type is EntityType.PROJECT:
        project = db.get(Project, entity_id)
        if project is None or project.deleted_at is not None:
            return None
        return join_documents(
            [
                project.title,
                project.summary,
                project.description,
                project.objectives,
                *_tag_names(db, [project.id], skills=True, user=False),
                *_tag_names(db, [project.id], skills=False, user=False),
            ]
        )

    if entity_type is EntityType.OPPORTUNITY:
        opportunity = db.get(Opportunity, entity_id)
        if opportunity is None:
            return None
        skills = list(
            db.execute(
                select(Skill.name)
                .join(OpportunitySkill, OpportunitySkill.skill_id == Skill.id)
                .where(OpportunitySkill.opportunity_id == opportunity.id)
            ).scalars()
        )
        return join_documents(
            [opportunity.title, opportunity.description, opportunity.eligibility, *skills]
        )

    if entity_type is EntityType.PUBLICATION:
        publication = db.get(Publication, entity_id)
        if publication is None:
            return None
        return join_documents([publication.title, publication.abstract, publication.venue])

    funding = db.get(FundingOpportunity, entity_id)
    if funding is None:
        return None
    areas = list(
        db.execute(
            select(ResearchArea.name)
            .join(FundingResearchArea, FundingResearchArea.research_area_id == ResearchArea.id)
            .where(FundingResearchArea.funding_id == funding.id)
        ).scalars()
    )
    return join_documents(
        [funding.title, funding.organization, funding.description, funding.eligibility, *areas]
    )


# --- writing embeddings ------------------------------------------------------


def embed_entity(db: Session, entity_type: EntityType, entity_id: uuid.UUID) -> bool:
    """(Re)embeds one entity. Returns True when a vector was written.

    Skips the work when the content hash is unchanged, which is what makes
    "re-embed on every save" affordable.
    """
    if not is_available():
        return False
    text = build_text(db, entity_type, entity_id)
    if not text:
        return False
    digest = content_hash(text)
    existing = db.execute(
        select(EntityEmbedding).where(
            EntityEmbedding.entity_type == entity_type,
            EntityEmbedding.entity_id == entity_id,
            EntityEmbedding.model_name == MODEL_NAME,
        )
    ).scalar_one_or_none()
    if existing is not None and existing.content_hash == digest:
        return False

    vector = embed_text(text)
    if vector is None:
        return False
    if existing is None:
        db.add(
            EntityEmbedding(
                entity_type=entity_type,
                entity_id=entity_id,
                model_name=MODEL_NAME,
                content_hash=digest,
                embedding=vector,
            )
        )
    else:
        existing.content_hash = digest
        existing.embedding = vector
    db.commit()
    return True


def embed_all(db: Session, entity_type: EntityType | None = None) -> dict[str, int]:
    """Backfill: embeds everything (skipping unchanged content)."""
    written: dict[str, int] = {}
    for kind in [entity_type] if entity_type else list(EntityType):
        ids = _all_ids(db, kind)
        count = sum(1 for entity_id in ids if embed_entity(db, kind, entity_id))
        written[kind.value] = count
    return written


def _all_ids(db: Session, entity_type: EntityType) -> list[uuid.UUID]:
    if entity_type is EntityType.RESEARCHER:
        return list(db.execute(select(ResearcherProfile.user_id)).scalars())
    if entity_type is EntityType.PROJECT:
        return list(db.execute(select(Project.id).where(Project.deleted_at.is_(None))).scalars())
    if entity_type is EntityType.OPPORTUNITY:
        return list(db.execute(select(Opportunity.id)).scalars())
    if entity_type is EntityType.PUBLICATION:
        return list(db.execute(select(Publication.id)).scalars())
    return list(db.execute(select(FundingOpportunity.id)).scalars())


# --- reading embeddings ------------------------------------------------------


def vector_neighbours(
    db: Session,
    query_vector: Sequence[float],
    entity_type: EntityType,
    limit: int = CANDIDATE_LIMIT,
) -> list[tuple[uuid.UUID, float]]:
    """(entity_id, similarity) ordered by cosine similarity, best first."""
    distance = EntityEmbedding.embedding.cosine_distance(list(query_vector))
    rows = db.execute(
        select(EntityEmbedding.entity_id, distance.label("distance"))
        .where(
            EntityEmbedding.entity_type == entity_type,
            EntityEmbedding.model_name == MODEL_NAME,
        )
        .order_by(distance)
        .limit(limit)
    ).all()
    # pgvector returns a distance in [0, 2]; similarity is the usual 1 - d.
    return [(entity_id, 1.0 - float(dist)) for entity_id, dist in rows]


def semantic_neighbours(
    db: Session,
    query: str,
    entity_type: EntityType,
    limit: int = CANDIDATE_LIMIT,
    *,
    min_similarity: float = MIN_SIMILARITY,
) -> list[tuple[uuid.UUID, float]]:
    """Nearest neighbours for a natural-language query, or [] without the extra."""
    vector = embed_text(query)
    if vector is None:
        return []
    return [
        (entity_id, similarity)
        for entity_id, similarity in vector_neighbours(db, vector, entity_type, limit)
        if similarity >= min_similarity
    ]


def embeddings_for(
    db: Session, entity_type: EntityType, entity_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[float]]:
    if not entity_ids:
        return {}
    rows = db.execute(
        select(EntityEmbedding.entity_id, EntityEmbedding.embedding).where(
            EntityEmbedding.entity_type == entity_type,
            EntityEmbedding.entity_id.in_(entity_ids),
            EntityEmbedding.model_name == MODEL_NAME,
        )
    ).all()
    return {entity_id: list(vector) for entity_id, vector in rows}


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Both sides are already L2-normalised, so this is just the dot product."""
    return float(sum(a * b for a, b in zip(left, right, strict=True)))


# --- fusion ------------------------------------------------------------------


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[uuid.UUID]], *, k: int = RRF_K
) -> list[uuid.UUID]:
    """Merges several ranked id lists into one.

    Each list contributes 1 / (k + rank) per item, so an item ranked well by
    both systems beats one ranked brilliantly by a single system. No score
    calibration between full-text rank and cosine similarity is needed --
    that's the point of RRF.
    """
    scores: dict[uuid.UUID, float] = {}
    first_seen: dict[uuid.UUID, int] = {}
    for ranking in rankings:
        for rank, entity_id in enumerate(ranking, start=1):
            scores[entity_id] = scores.get(entity_id, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(entity_id, rank)
    return sorted(scores, key=lambda entity_id: (-scores[entity_id], first_seen[entity_id]))


def embed_query_batch(texts: Sequence[str]) -> list[list[float]] | None:
    return embed_texts(texts)
