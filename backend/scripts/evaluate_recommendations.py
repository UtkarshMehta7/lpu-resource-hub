"""Offline evaluation of the recommender against hand-labelled fixtures.

Runs the real scoring code (app/ml) over `fixtures/recommendation_eval.json`
and reports precision@5 and nDCG@10, so a weight or scoring change can be
compared against a fixed baseline. No database and no network.

Usage:  python -m scripts.evaluate_recommendations [--json]
"""

from __future__ import annotations

import argparse
import json
import math
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.ml.embeddings import embed_texts, is_available
from app.ml.features import (
    OPTIONAL_WEIGHT,
    REQUIRED_WEIGHT,
    ItemFeatures,
    ScoreWeights,
    ViewerFeatures,
)
from app.ml.recommender import Recommender
from app.ml.tfidf import TfidfIndex

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "recommendation_eval.json"
NAMESPACE = uuid.UUID("11111111-2222-3333-4444-555555555555")
# A judgement of 2 or 3 counts as relevant for precision@5.
RELEVANT_FROM = 2
PRECISION_AT = 5
NDCG_AT = 10
# Share of the score given to semantic similarity in the hybrid run; matches
# the app's default (Settings.rec_semantic_weight).
SEMANTIC_SHARE = 0.25


def _id(name: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, name)


def load_fixture(path: Path = FIXTURE) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def build_world(
    data: Mapping[str, Any],
) -> tuple[
    list[ItemFeatures],
    dict[uuid.UUID, uuid.UUID | None],
    dict[uuid.UUID, str],
    dict[uuid.UUID, str],
    TfidfIndex | None,
]:
    parents = {
        _id(area): (_id(parent) if parent else None) for area, parent in data["areas"].items()
    }
    area_names = {_id(area): area for area in data["areas"]}
    skill_names: dict[uuid.UUID, str] = {}
    items: list[ItemFeatures] = []
    for raw in data["items"]:
        skills: dict[uuid.UUID, float] = {}
        required: set[uuid.UUID] = set()
        for skill, kind in raw["skills"].items():
            skill_names[_id(skill)] = skill
            skills[_id(skill)] = REQUIRED_WEIGHT if kind == "required" else OPTIONAL_WEIGHT
            if kind == "required":
                required.add(_id(skill))
        items.append(
            ItemFeatures(
                item_id=_id(raw["id"]),
                skills=skills,
                required_skills=required,
                research_areas={_id(area) for area in raw["areas"]},
                text=raw["text"],
            )
        )
    index = TfidfIndex.build([(item.item_id, item.text) for item in items])
    return items, parents, skill_names, area_names, index


def viewer_features(raw: Mapping[str, Any]) -> ViewerFeatures:
    return ViewerFeatures(
        user_id=_id(raw["id"]),
        skills={_id(skill): int(level) for skill, level in raw["skills"].items()},
        research_areas={_id(area) for area in raw["areas"]},
        text=raw["text"],
    )


def precision_at_k(ranked: Sequence[int], k: int) -> float:
    top = ranked[:k]
    if not top:
        return 0.0
    return sum(1 for grade in top if grade >= RELEVANT_FROM) / len(top)


def ndcg_at_k(ranked: Sequence[int], ideal: Sequence[int], k: int) -> float:
    def dcg(grades: Sequence[int]) -> float:
        return sum(
            (2**grade - 1) / math.log2(position + 2) for position, grade in enumerate(grades)
        )

    best = dcg(sorted(ideal, reverse=True)[:k])
    return dcg(ranked[:k]) / best if best else 0.0


def semantic_scores(
    data: Mapping[str, Any], viewer_text: str, items: Sequence[ItemFeatures]
) -> dict[uuid.UUID, float]:
    """Cosine similarity between a viewer's text and each item's text.

    Uses the same model as the running app. Returns {} when the optional ML
    extra isn't installed, which makes the hybrid run degrade to Phase 1.
    """
    del data
    vectors = embed_texts([viewer_text, *[item.text for item in items]])
    if vectors is None:
        return {}
    viewer_vector, *item_vectors = vectors
    return {
        item.item_id: float(sum(a * b for a, b in zip(viewer_vector, vector, strict=True)))
        for item, vector in zip(items, item_vectors, strict=True)
    }


def evaluate(
    data: Mapping[str, Any],
    weights: ScoreWeights | None = None,
    *,
    semantic: bool = False,
) -> dict[str, Any]:
    items, parents, skill_names, area_names, index = build_world(data)
    weights = weights or ScoreWeights()
    if semantic:
        weights = weights.with_semantic(SEMANTIC_SHARE)
    recommender = Recommender(weights)
    per_viewer: list[dict[str, Any]] = []
    for raw in data["viewers"]:
        viewer = viewer_features(raw)
        judgements = {_id(name): grade for name, grade in raw["relevance"].items()}
        ranked = recommender.recommend(
            viewer,
            items,
            len(items),
            area_parents=parents,
            skill_names=skill_names,
            area_names=area_names,
            index=index,
            semantic_scores=semantic_scores(data, raw["text"], items) if semantic else None,
        )
        grades = [judgements.get(scored.item_id, 0) for scored in ranked]
        per_viewer.append(
            {
                "viewer": raw["id"],
                "precision_at_5": round(precision_at_k(grades, PRECISION_AT), 4),
                "ndcg_at_10": round(ndcg_at_k(grades, list(judgements.values()), NDCG_AT), 4),
                "top_5": [
                    {
                        "item": next(
                            name for name in raw["relevance"] if _id(name) == scored.item_id
                        ),
                        "score": scored.score,
                        "reasons": scored.reasons,
                    }
                    for scored in ranked[:PRECISION_AT]
                ],
            }
        )
    count = len(per_viewer) or 1
    return {
        "mode": "hybrid" if semantic else "phase1",
        "viewers": per_viewer,
        "mean_precision_at_5": round(sum(v["precision_at_5"] for v in per_viewer) / count, 4),
        "mean_ndcg_at_10": round(sum(v["ndcg_at_10"] for v in per_viewer) / count, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print raw JSON results")
    parser.add_argument(
        "--compare",
        action="store_true",
        help="run Phase 1 and the hybrid (semantic) scorer side by side",
    )
    args = parser.parse_args()

    data = load_fixture()
    runs = [evaluate(data)]
    if args.compare:
        if not is_available():
            print('The ML extra isn\'t installed; run: pip install -e ".[ml]"')
            return
        runs.append(evaluate(data, semantic=True))

    if args.json:
        print(json.dumps(runs if args.compare else runs[0], indent=2))
        return

    print(f"{'mode':<10}{'viewer':<24}{'P@5':>8}{'nDCG@10':>10}")
    for results in runs:
        for row in results["viewers"]:
            print(
                f"{results['mode']:<10}{row['viewer']:<24}"
                f"{row['precision_at_5']:>8}{row['ndcg_at_10']:>10}"
            )
        print(
            f"{results['mode']:<10}{'mean':<24}"
            f"{results['mean_precision_at_5']:>8}{results['mean_ndcg_at_10']:>10}\n"
        )
    results = runs[0]
    print("\nTop 5 with reasons:")
    for row in results["viewers"]:
        print(f"\n{row['viewer']}:")
        for entry in row["top_5"]:
            print(f"  {entry['item']:<24} {entry['score']:.4f}  {entry['reasons'][0]}")


if __name__ == "__main__":
    main()
