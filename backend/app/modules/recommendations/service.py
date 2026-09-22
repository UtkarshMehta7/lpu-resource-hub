"""Turns database rows into features, applies the business filters, and
ranks with app/ml. Services never import FastAPI.

Two rules shape everything here:

* Filters run in SQL, before scoring, so a hidden project or an ineligible
  opportunity can never reach the ranker (and so can never be "explained").
* Explanations come from the score breakdown only.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ml.explain import COLD_START_REASON
from app.ml.features import (
    OPTIONAL_WEIGHT,
    REQUIRED_WEIGHT,
    ItemFeatures,
    ScoreWeights,
    ViewerFeatures,
)
from app.ml.preprocessing import join_documents
from app.ml.recommender import Recommender, ScoredItem
from app.ml.tfidf import INDEX_CACHE
from app.modules.applications.models import Application
from app.modules.collaborations.models import CollaborationRequest, CollaborationStatus
from app.modules.opportunities.models import (
    STUDENT_TYPES,
    Opportunity,
    OpportunitySkill,
    OpportunityStatus,
    OpportunityType,
)
from app.modules.opportunities.policies import visibility_filter as opportunity_visibility
from app.modules.opportunities.service import opportunity_cards
from app.modules.profiles.models import (
    ResearcherProfile,
    StudentProfile,
    UserResearchArea,
    UserSkill,
)
from app.modules.projects.models import (
    Project,
    ProjectMember,
    ProjectResearchArea,
    ProjectSkill,
    ProjectStatus,
)
from app.modules.projects.policies import visibility_filter as project_visibility
from app.modules.projects.service import project_cards
from app.modules.publications.models import Publication, PublicationAuthor
from app.modules.recommendations.schemas import (
    Recommendation,
    RecommendationsResponse,
    RecommendedItem,
    TargetType,
)
from app.modules.researchers.directory import cards_for_researchers, cards_for_students
from app.modules.taxonomy.models import ResearchArea, Skill
from app.modules.users.models import User, UserRole

RESEARCHER_ROLES = (UserRole.FACULTY, UserRole.RESEARCH_COORDINATOR)


@dataclass(frozen=True, slots=True)
class Candidates:
    """What a target type contributes: features to score, and the newest-first
    order used when the viewer's profile is too sparse to rank on."""

    features: list[ItemFeatures]
    newest_ids: list[uuid.UUID]


# --- shared lookups ----------------------------------------------------------


def area_parents(db: Session) -> dict[uuid.UUID, uuid.UUID | None]:
    return {
        area_id: parent_id
        for area_id, parent_id in db.execute(select(ResearchArea.id, ResearchArea.parent_id)).all()
    }


def tag_names(db: Session) -> tuple[dict[uuid.UUID, str], dict[uuid.UUID, str]]:
    skills = {sid: name for sid, name in db.execute(select(Skill.id, Skill.name)).all()}
    areas = {
        aid: name for aid, name in db.execute(select(ResearchArea.id, ResearchArea.name)).all()
    }
    return skills, areas


def _skills_by_user(
    db: Session, user_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, dict[uuid.UUID, int]]:
    result: dict[uuid.UUID, dict[uuid.UUID, int]] = {}
    if not user_ids:
        return result
    for user_id, skill_id, proficiency in db.execute(
        select(UserSkill.user_id, UserSkill.skill_id, UserSkill.proficiency).where(
            UserSkill.user_id.in_(user_ids)
        )
    ).all():
        result.setdefault(user_id, {})[skill_id] = proficiency
    return result


def _areas_by_user(db: Session, user_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, set[uuid.UUID]]:
    result: dict[uuid.UUID, set[uuid.UUID]] = {}
    if not user_ids:
        return result
    for user_id, area_id in db.execute(
        select(UserResearchArea.user_id, UserResearchArea.research_area_id).where(
            UserResearchArea.user_id.in_(user_ids)
        )
    ).all():
        result.setdefault(user_id, set()).add(area_id)
    return result


def _user_documents(db: Session, user_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
    """A person's own words: profile bio/interests plus their publications."""
    parts: dict[uuid.UUID, list[str]] = {user_id: [] for user_id in user_ids}
    if not user_ids:
        return {}
    for user_id, bio in db.execute(
        select(ResearcherProfile.user_id, ResearcherProfile.bio).where(
            ResearcherProfile.user_id.in_(user_ids)
        )
    ).all():
        parts[user_id].append(bio or "")
    for user_id, bio, interests in db.execute(
        select(StudentProfile.user_id, StudentProfile.bio, StudentProfile.interests).where(
            StudentProfile.user_id.in_(user_ids)
        )
    ).all():
        parts[user_id].extend([bio or "", interests or ""])
    for user_id, title, abstract in db.execute(
        select(PublicationAuthor.user_id, Publication.title, Publication.abstract)
        .join(Publication, Publication.id == PublicationAuthor.publication_id)
        .where(PublicationAuthor.user_id.in_(user_ids))
    ).all():
        if user_id is not None:
            parts[user_id].extend([title, abstract or ""])
    return {user_id: join_documents(values) for user_id, values in parts.items()}


def _user_features(db: Session, user_ids: Sequence[uuid.UUID]) -> list[ItemFeatures]:
    skills = _skills_by_user(db, user_ids)
    areas = _areas_by_user(db, user_ids)
    documents = _user_documents(db, user_ids)
    return [
        ItemFeatures(
            item_id=user_id,
            skills={sid: REQUIRED_WEIGHT for sid in skills.get(user_id, {})},
            research_areas=areas.get(user_id, set()),
            text=documents.get(user_id, ""),
        )
        for user_id in user_ids
    ]


def viewer_features(db: Session, viewer: User) -> ViewerFeatures:
    return ViewerFeatures(
        user_id=viewer.id,
        skills=_skills_by_user(db, [viewer.id]).get(viewer.id, {}),
        research_areas=_areas_by_user(db, [viewer.id]).get(viewer.id, set()),
        text=_user_documents(db, [viewer.id]).get(viewer.id, ""),
    )


# --- candidate sets (filters live here, in SQL) ------------------------------


def _researcher_candidates(db: Session, viewer: User) -> Candidates:
    rows = (
        db.execute(
            select(User.id)
            .join(ResearcherProfile, ResearcherProfile.user_id == User.id)
            .where(User.is_active.is_(True), User.role.in_(RESEARCHER_ROLES), User.id != viewer.id)
            .order_by(ResearcherProfile.created_at.desc())
        )
        .scalars()
        .all()
    )
    return Candidates(features=_user_features(db, list(rows)), newest_ids=list(rows))


def _collaborator_candidates(db: Session, viewer: User) -> Candidates:
    """People the viewer could actually send a collaboration request to
    (Step 8 rules), minus anyone there's already an open or accepted request
    with. Admins can't send, so they get nothing."""
    if viewer.role is UserRole.ADMIN:
        return Candidates(features=[], newest_ids=[])
    engaged = (
        select(CollaborationRequest.recipient_id)
        .where(
            CollaborationRequest.sender_id == viewer.id,
            CollaborationRequest.status.in_(
                (CollaborationStatus.PENDING, CollaborationStatus.ACCEPTED)
            ),
        )
        .union(
            select(CollaborationRequest.sender_id).where(
                CollaborationRequest.recipient_id == viewer.id,
                CollaborationRequest.status.in_(
                    (CollaborationStatus.PENDING, CollaborationStatus.ACCEPTED)
                ),
            )
        )
    )
    contactable = or_(
        User.id.in_(select(ResearcherProfile.user_id)),
        User.id.in_(select(StudentProfile.user_id).where(StudentProfile.is_discoverable.is_(True))),
    )
    rows = (
        db.execute(
            select(User.id)
            .where(
                User.is_active.is_(True),
                User.role != UserRole.ADMIN,
                User.id != viewer.id,
                User.id.not_in(engaged),
                contactable,
            )
            .order_by(User.created_at.desc())
        )
        .scalars()
        .all()
    )
    return Candidates(features=_user_features(db, list(rows)), newest_ids=list(rows))


def _project_candidates(db: Session, viewer: User) -> Candidates:
    projects = (
        db.execute(
            select(Project)
            .where(
                Project.deleted_at.is_(None),
                Project.status == ProjectStatus.ACTIVE,
                Project.owner_id != viewer.id,
                Project.id.not_in(
                    select(ProjectMember.project_id).where(ProjectMember.user_id == viewer.id)
                ),
                project_visibility(viewer),
            )
            .order_by(Project.created_at.desc())
        )
        .scalars()
        .all()
    )
    ids = [project.id for project in projects]
    skills: dict[uuid.UUID, dict[uuid.UUID, float]] = {}
    for project_id, skill_id in db.execute(
        select(ProjectSkill.project_id, ProjectSkill.skill_id).where(
            ProjectSkill.project_id.in_(ids)
        )
    ).all():
        skills.setdefault(project_id, {})[skill_id] = REQUIRED_WEIGHT
    areas: dict[uuid.UUID, set[uuid.UUID]] = {}
    for project_id, area_id in db.execute(
        select(ProjectResearchArea.project_id, ProjectResearchArea.research_area_id).where(
            ProjectResearchArea.project_id.in_(ids)
        )
    ).all():
        areas.setdefault(project_id, set()).add(area_id)
    return Candidates(
        features=[
            ItemFeatures(
                item_id=project.id,
                skills=skills.get(project.id, {}),
                research_areas=areas.get(project.id, set()),
                text=join_documents(
                    [project.title, project.summary, project.description, project.objectives]
                ),
            )
            for project in projects
        ],
        newest_ids=ids,
    )


def opportunity_features(db: Session, opportunity: Opportunity) -> ItemFeatures:
    """Features for one opening: required skills count double the optional ones.

    Shared with the "relevant opportunity" notification (Step 12) so a
    notification and a recommendation always agree about the same opening.
    """
    skills: dict[uuid.UUID, float] = {}
    required: set[uuid.UUID] = set()
    for skill_id, is_required in db.execute(
        select(OpportunitySkill.skill_id, OpportunitySkill.is_required).where(
            OpportunitySkill.opportunity_id == opportunity.id
        )
    ).all():
        skills[skill_id] = REQUIRED_WEIGHT if is_required else OPTIONAL_WEIGHT
        if is_required:
            required.add(skill_id)
    return ItemFeatures(
        item_id=opportunity.id,
        skills=skills,
        required_skills=required,
        research_areas=set(),
        text=join_documents([opportunity.title, opportunity.description, opportunity.eligibility]),
    )


def eligible_opportunity_types(viewer: User) -> tuple[OpportunityType, ...]:
    """Which opening types this role may apply to (Step 7 rules)."""
    if viewer.role is UserRole.STUDENT:
        return tuple(sorted(STUDENT_TYPES, key=str))
    if viewer.role in RESEARCHER_ROLES:
        return (OpportunityType.COLLABORATION,)
    return ()


def _opportunity_candidates(db: Session, viewer: User) -> Candidates:
    eligible = eligible_opportunity_types(viewer)
    if not eligible:
        return Candidates(features=[], newest_ids=[])
    opportunities = (
        db.execute(
            select(Opportunity)
            .where(
                Opportunity.status == OpportunityStatus.OPEN,
                Opportunity.deadline >= datetime.now(UTC).date(),
                Opportunity.opportunity_type.in_(eligible),
                Opportunity.created_by != viewer.id,
                Opportunity.id.not_in(
                    select(Application.opportunity_id).where(Application.applicant_id == viewer.id)
                ),
                opportunity_visibility(viewer),
            )
            .order_by(Opportunity.created_at.desc())
        )
        .scalars()
        .all()
    )
    return Candidates(
        features=[opportunity_features(db, opportunity) for opportunity in opportunities],
        newest_ids=[opportunity.id for opportunity in opportunities],
    )


_CANDIDATE_BUILDERS = {
    TargetType.RESEARCHERS: _researcher_candidates,
    TargetType.COLLABORATORS: _collaborator_candidates,
    TargetType.PROJECTS: _project_candidates,
    TargetType.OPPORTUNITIES: _opportunity_candidates,
}


# --- TF-IDF corpus + cache ---------------------------------------------------


def _fingerprint(db: Session, target: TargetType) -> tuple[int, str]:
    """Cheap "has anything changed?" signal: row count + newest timestamp."""
    if target in (TargetType.RESEARCHERS, TargetType.COLLABORATORS):
        counts = db.execute(select(func.count(), func.max(ResearcherProfile.updated_at))).one()
        publications = db.execute(select(func.count(), func.max(Publication.updated_at))).one()
        return (counts[0] + publications[0], f"{counts[1]}|{publications[1]}")
    model = Project if target is TargetType.PROJECTS else Opportunity
    count, newest = db.execute(select(func.count(), func.max(model.updated_at))).one()
    return (count, str(newest))


def _corpus(db: Session, target: TargetType) -> list[tuple[uuid.UUID, str]]:
    """Every document of this kind, so term statistics don't shift per viewer.

    Only candidate ids are ever looked up in the resulting index, so
    including non-visible rows here can't leak their content.
    """
    if target in (TargetType.RESEARCHERS, TargetType.COLLABORATORS):
        user_ids = list(db.execute(select(User.id).where(User.is_active.is_(True))).scalars().all())
        return list(_user_documents(db, user_ids).items())
    if target is TargetType.PROJECTS:
        return [
            (
                project.id,
                join_documents(
                    [project.title, project.summary, project.description, project.objectives]
                ),
            )
            for project in db.execute(select(Project).where(Project.deleted_at.is_(None))).scalars()
        ]
    return [
        (
            opportunity.id,
            join_documents([opportunity.title, opportunity.description, opportunity.eligibility]),
        )
        for opportunity in db.execute(select(Opportunity)).scalars()
    ]


# --- cards -------------------------------------------------------------------


def _cards(
    db: Session, viewer: User, target: TargetType, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, RecommendedItem]:
    if not ids:
        return {}
    cards: dict[uuid.UUID, RecommendedItem] = {}
    if target in (TargetType.RESEARCHERS, TargetType.COLLABORATORS):
        for researcher in cards_for_researchers(db, ids):
            cards[researcher.user_id] = researcher
        if target is TargetType.COLLABORATORS:
            for student in cards_for_students(db, ids):
                cards[student.user_id] = student
        return cards
    if target is TargetType.PROJECTS:
        projects = db.execute(select(Project).where(Project.id.in_(ids))).scalars().all()
        for card in project_cards(db, list(projects)):
            cards[card.id] = card
        return cards
    opportunities = db.execute(select(Opportunity).where(Opportunity.id.in_(ids))).scalars().all()
    for opportunity_card in opportunity_cards(db, viewer, list(opportunities)):
        cards[opportunity_card.id] = opportunity_card
    return cards


# --- entry point -------------------------------------------------------------


def recommend(
    db: Session, viewer: User, target: TargetType, limit: int, weights: ScoreWeights
) -> RecommendationsResponse:
    candidates = _CANDIDATE_BUILDERS[target](db, viewer)
    features = viewer_features(db, viewer)

    if features.is_cold:
        chosen = candidates.newest_ids[:limit]
        cards = _cards(db, viewer, target, chosen)
        return RecommendationsResponse(
            type=target,
            cold_start=True,
            items=[
                Recommendation(item_id=item_id, score=0.0, reasons=[COLD_START_REASON], item=card)
                for item_id in chosen
                if (card := cards.get(item_id)) is not None
            ],
        )

    index = INDEX_CACHE.get_or_build(target.value, _fingerprint(db, target), _corpus(db, target))
    skill_names, area_names = tag_names(db)
    ranked: list[ScoredItem] = Recommender(weights).recommend(
        features,
        candidates.features,
        limit,
        area_parents=area_parents(db),
        skill_names=skill_names,
        area_names=area_names,
        index=index,
    )
    cards = _cards(db, viewer, target, [item.item_id for item in ranked])
    return RecommendationsResponse(
        type=target,
        cold_start=False,
        items=[
            Recommendation(item_id=item.item_id, score=item.score, reasons=item.reasons, item=card)
            for item in ranked
            if (card := cards.get(item.item_id)) is not None
        ],
    )
