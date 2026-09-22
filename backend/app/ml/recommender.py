"""Ranking, independent of where the features came from."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.ml.explain import build_reasons
from app.ml.features import Breakdown, ItemFeatures, ScoreWeights, ViewerFeatures
from app.ml.scoring import score_item
from app.ml.tfidf import TfidfIndex

MIN_SCORE = 1e-9


@dataclass(frozen=True, slots=True)
class ScoredItem:
    item_id: uuid.UUID
    score: float
    reasons: list[str]
    breakdown: Breakdown


class Recommender:
    """Scores candidate items for one viewer and returns the top k.

    Takes features rather than a database session (the roadmap's
    `recommend(user, target_type, k)` lives one layer up, in
    `app/modules/recommendations/service.py`), which keeps this class
    testable and lets the offline evaluation reuse it unchanged.
    """

    def __init__(self, weights: ScoreWeights) -> None:
        self.weights = weights

    def recommend(
        self,
        viewer: ViewerFeatures,
        items: Sequence[ItemFeatures],
        k: int,
        *,
        area_parents: Mapping[uuid.UUID, uuid.UUID | None],
        skill_names: Mapping[uuid.UUID, str],
        area_names: Mapping[uuid.UUID, str],
        index: TfidfIndex | None = None,
    ) -> list[ScoredItem]:
        similarities = index.similarities(viewer.text) if index else {}
        scored: list[ScoredItem] = []
        for item in items:
            text_score = similarities.get(item.item_id, 0.0)
            terms = (
                index.top_terms(viewer.text, item.item_id)
                if index is not None and text_score > MIN_SCORE
                else ()
            )
            breakdown = score_item(
                viewer, item, area_parents, self.weights, text_score=text_score, related_terms=terms
            )
            if breakdown.score <= MIN_SCORE:
                continue
            scored.append(
                ScoredItem(
                    item_id=item.item_id,
                    score=round(breakdown.score, 6),
                    reasons=build_reasons(breakdown, skill_names, area_names),
                    breakdown=breakdown,
                )
            )
        # Ties break on id so the same inputs always give the same order.
        scored.sort(key=lambda item: (-item.score, str(item.item_id)))
        return scored[:k]
