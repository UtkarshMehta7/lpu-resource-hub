"""Feature shapes shared by scoring, explanations and the recommender.

Keeping these DB-free is what lets the offline evaluation script
(`scripts/evaluate_recommendations.py`) run the real scoring code against
hand-labelled fixtures.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

# How an opportunity's required vs. optional skills are weighted.
REQUIRED_WEIGHT = 1.0
OPTIONAL_WEIGHT = 0.5


@dataclass(frozen=True, slots=True)
class ViewerFeatures:
    """The person we're recommending for."""

    user_id: uuid.UUID
    # skill id -> self-reported proficiency (1-5)
    skills: dict[uuid.UUID, int] = field(default_factory=dict)
    research_areas: set[uuid.UUID] = field(default_factory=set)
    text: str = ""

    @property
    def is_cold(self) -> bool:
        """Too little signal to rank on: fall back to newest items."""
        return len(self.skills) < 3 and len(self.research_areas) < 3 and not self.text.strip()


@dataclass(frozen=True, slots=True)
class ItemFeatures:
    """One candidate: a researcher, project, opportunity or collaborator."""

    item_id: uuid.UUID
    # skill id -> weight (required skills count double the optional ones)
    skills: dict[uuid.UUID, float] = field(default_factory=dict)
    required_skills: set[uuid.UUID] = field(default_factory=set)
    research_areas: set[uuid.UUID] = field(default_factory=set)
    text: str = ""


@dataclass(frozen=True, slots=True)
class ScoreWeights:
    skill: float = 0.40
    area: float = 0.35
    text: float = 0.25
    # Step 13: semantic similarity, 0 when embeddings aren't installed.
    semantic: float = 0.0

    def with_semantic(self, share: float) -> ScoreWeights:
        """Gives `share` of the total to semantic similarity, scaling the rest.

        One knob instead of four: the structured and lexical weights keep
        their relative proportions, so turning embeddings on doesn't silently
        re-tune the Step 9 scoring.
        """
        if share <= 0:
            return self
        keep = 1.0 - share
        return ScoreWeights(
            skill=self.skill * keep,
            area=self.area * keep,
            text=self.text * keep,
            semantic=share,
        )


@dataclass(frozen=True, slots=True)
class Breakdown:
    """Why an item scored what it did. Explanations may only use this."""

    score: float
    skill_score: float
    area_score: float
    text_score: float
    semantic_score: float = 0.0
    matched_required: tuple[uuid.UUID, ...] = ()
    total_required: int = 0
    matched_optional: tuple[uuid.UUID, ...] = ()
    shared_areas: tuple[uuid.UUID, ...] = ()
    related_areas: tuple[uuid.UUID, ...] = ()
    related_terms: tuple[str, ...] = ()
