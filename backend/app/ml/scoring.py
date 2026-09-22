"""Score components. Deterministic, and every number here is explainable.

score = w_skill * skill_score + w_area * area_score + w_text * text_score
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from app.ml.features import Breakdown, ItemFeatures, ScoreWeights, ViewerFeatures

# An area that is the parent or child of one of yours is a partial match.
PARENT_CREDIT = 0.5


def proficiency_factor(proficiency: int) -> float:
    """1 (beginner) -> 0.5, 5 (expert) -> 1.0. Having the skill always counts
    for something; being good at it counts double."""
    clamped = min(max(proficiency, 1), 5)
    return 0.5 + 0.5 * (clamped - 1) / 4


def skill_score(viewer: ViewerFeatures, item: ItemFeatures) -> float:
    """Weighted share of the item's skills the viewer has, scaled by how
    strong they say they are. Items asking for nothing score 0, not 1:
    there's no evidence of a match."""
    if not item.skills:
        return 0.0
    total = sum(item.skills.values())
    matched = sum(
        weight * proficiency_factor(viewer.skills[skill_id])
        for skill_id, weight in item.skills.items()
        if skill_id in viewer.skills
    )
    return matched / total if total else 0.0


def area_score(
    viewer: ViewerFeatures, item: ItemFeatures, parents: Mapping[uuid.UUID, uuid.UUID | None]
) -> float:
    """Jaccard over research areas, with partial credit where one area is the
    parent of the other (the taxonomy is two levels deep, Step 3)."""
    if not viewer.research_areas or not item.research_areas:
        return 0.0
    shared = viewer.research_areas & item.research_areas
    related = _related_areas(viewer.research_areas, item.research_areas, parents)
    union = viewer.research_areas | item.research_areas
    return (len(shared) + PARENT_CREDIT * len(related)) / len(union)


def _related_areas(
    viewer_areas: set[uuid.UUID],
    item_areas: set[uuid.UUID],
    parents: Mapping[uuid.UUID, uuid.UUID | None],
) -> set[uuid.UUID]:
    """Item areas that aren't shared but sit next to one of the viewer's."""
    viewer_parents = {parents.get(area) for area in viewer_areas} - {None}
    related: set[uuid.UUID] = set()
    for area in item_areas - viewer_areas:
        if parents.get(area) in viewer_areas or area in viewer_parents:
            related.add(area)
    return related


def score_item(
    viewer: ViewerFeatures,
    item: ItemFeatures,
    parents: Mapping[uuid.UUID, uuid.UUID | None],
    weights: ScoreWeights,
    text_score: float = 0.0,
    related_terms: tuple[str, ...] = (),
) -> Breakdown:
    skills = skill_score(viewer, item)
    areas = area_score(viewer, item, parents)
    matched = {sid for sid in item.skills if sid in viewer.skills}
    shared = viewer.research_areas & item.research_areas
    related = _related_areas(viewer.research_areas, item.research_areas, parents)
    return Breakdown(
        score=weights.skill * skills + weights.area * areas + weights.text * text_score,
        skill_score=skills,
        area_score=areas,
        text_score=text_score,
        matched_required=tuple(sorted(matched & item.required_skills, key=str)),
        total_required=len(item.required_skills),
        matched_optional=tuple(sorted(matched - item.required_skills, key=str)),
        shared_areas=tuple(sorted(shared, key=str)),
        related_areas=tuple(sorted(related, key=str)),
        related_terms=related_terms,
    )
