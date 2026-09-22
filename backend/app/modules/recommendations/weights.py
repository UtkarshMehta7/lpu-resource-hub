"""Score weights, in one place.

The Step 9 weights are the baseline; when embeddings are installed a share of
the total moves to semantic similarity and the rest keeps its proportions
(`ScoreWeights.with_semantic`). Building them here means the recommendations
endpoint, the dashboard and the "relevant opportunity" notification can never
disagree about how something is scored.
"""

from __future__ import annotations

from app.core.config import Settings
from app.ml.embeddings import is_available
from app.ml.features import ScoreWeights


def score_weights(settings: Settings) -> ScoreWeights:
    base = ScoreWeights(
        skill=settings.rec_weight_skill,
        area=settings.rec_weight_area,
        text=settings.rec_weight_text,
    )
    if not is_available():
        return base
    return base.with_semantic(settings.rec_semantic_weight)
