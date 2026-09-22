"""Pure scoring, explanations and ranking -- no database, fully deterministic."""

from __future__ import annotations

import uuid

import pytest

from app.ml.explain import build_reasons
from app.ml.features import ItemFeatures, ScoreWeights, ViewerFeatures
from app.ml.recommender import Recommender
from app.ml.scoring import area_score, proficiency_factor, score_item, skill_score
from app.ml.tfidf import TfidfIndex
from scripts.evaluate_recommendations import evaluate, load_fixture

PYTHON = uuid.UUID("00000000-0000-0000-0000-00000000aa01")
DOCKER = uuid.UUID("00000000-0000-0000-0000-00000000aa02")
AWS = uuid.UUID("00000000-0000-0000-0000-00000000aa03")
ML = uuid.UUID("00000000-0000-0000-0000-00000000bb01")
DEEP_LEARNING = uuid.UUID("00000000-0000-0000-0000-00000000bb02")
CHEMISTRY = uuid.UUID("00000000-0000-0000-0000-00000000bb03")

PARENTS: dict[uuid.UUID, uuid.UUID | None] = {ML: None, DEEP_LEARNING: ML, CHEMISTRY: None}
SKILL_NAMES = {PYTHON: "Python", DOCKER: "Docker", AWS: "AWS"}
AREA_NAMES = {ML: "Machine Learning", DEEP_LEARNING: "Deep Learning", CHEMISTRY: "Chemistry"}


def viewer(**kwargs: object) -> ViewerFeatures:
    defaults: dict[str, object] = {
        "user_id": uuid.UUID("00000000-0000-0000-0000-0000000000ff"),
        "skills": {PYTHON: 5, DOCKER: 3},
        "research_areas": {ML},
        "text": "python services for machine learning",
    }
    return ViewerFeatures(**{**defaults, **kwargs})  # type: ignore[arg-type]


def test_proficiency_is_monotonic_and_bounded() -> None:
    assert proficiency_factor(1) == pytest.approx(0.5)
    assert proficiency_factor(5) == pytest.approx(1.0)
    assert proficiency_factor(3) == pytest.approx(0.75)
    # Out-of-range values are clamped rather than distorting a score.
    assert proficiency_factor(0) == proficiency_factor(1)
    assert proficiency_factor(9) == proficiency_factor(5)


def test_skill_score_weights_required_above_optional() -> None:
    required_only = ItemFeatures(
        item_id=uuid.uuid4(), skills={PYTHON: 1.0, AWS: 1.0}, required_skills={PYTHON, AWS}
    )
    with_optional = ItemFeatures(
        item_id=uuid.uuid4(), skills={PYTHON: 1.0, AWS: 0.5}, required_skills={PYTHON}
    )
    # Missing AWS costs less when it's only "nice to have".
    assert skill_score(viewer(), with_optional) > skill_score(viewer(), required_only)


def test_skill_score_is_proficiency_aware() -> None:
    item = ItemFeatures(item_id=uuid.uuid4(), skills={PYTHON: 1.0}, required_skills={PYTHON})
    expert = skill_score(viewer(skills={PYTHON: 5}), item)
    beginner = skill_score(viewer(skills={PYTHON: 1}), item)
    assert expert == pytest.approx(1.0)
    assert beginner == pytest.approx(0.5)


def test_items_asking_for_nothing_score_zero_on_skills() -> None:
    assert skill_score(viewer(), ItemFeatures(item_id=uuid.uuid4())) == 0.0


def test_area_score_gives_partial_credit_to_a_child_area() -> None:
    exact = ItemFeatures(item_id=uuid.uuid4(), research_areas={ML})
    child = ItemFeatures(item_id=uuid.uuid4(), research_areas={DEEP_LEARNING})
    unrelated = ItemFeatures(item_id=uuid.uuid4(), research_areas={CHEMISTRY})
    assert area_score(viewer(), exact, PARENTS) == pytest.approx(1.0)
    assert area_score(viewer(), child, PARENTS) == pytest.approx(0.25)
    assert area_score(viewer(), unrelated, PARENTS) == 0.0


def test_reasons_only_mention_what_actually_matched() -> None:
    item = ItemFeatures(
        item_id=uuid.uuid4(),
        skills={PYTHON: 1.0, AWS: 1.0, DOCKER: 0.5},
        required_skills={PYTHON, AWS},
        research_areas={DEEP_LEARNING},
        text="python containers",
    )
    breakdown = score_item(
        viewer(), item, PARENTS, ScoreWeights(), text_score=0.4, related_terms=("containers",)
    )
    reasons = build_reasons(breakdown, SKILL_NAMES, AREA_NAMES)
    assert reasons[0] == "Matches 1 of 2 required skills: Python"
    assert "Also has: Docker" in reasons
    assert "Related research area: Deep Learning" in reasons
    assert "Related terms: containers" in reasons
    # AWS is required but missing, so it is never claimed as a match.
    assert not any("AWS" in reason for reason in reasons)


def test_a_zero_score_item_is_dropped_not_explained() -> None:
    unrelated = ItemFeatures(item_id=uuid.uuid4(), research_areas={CHEMISTRY}, text="titration")
    ranked = Recommender(ScoreWeights()).recommend(
        viewer(),
        [unrelated],
        5,
        area_parents=PARENTS,
        skill_names=SKILL_NAMES,
        area_names=AREA_NAMES,
        index=None,
    )
    assert ranked == []


def test_ranking_is_deterministic_and_ordered_by_score() -> None:
    strong = ItemFeatures(
        item_id=uuid.UUID("00000000-0000-0000-0000-0000000000a1"),
        skills={PYTHON: 1.0},
        required_skills={PYTHON},
        research_areas={ML},
        text="python machine learning",
    )
    weak = ItemFeatures(
        item_id=uuid.UUID("00000000-0000-0000-0000-0000000000a2"),
        skills={DOCKER: 1.0},
        required_skills={DOCKER},
        research_areas={DEEP_LEARNING},
        text="containers",
    )
    index = TfidfIndex.build([(strong.item_id, strong.text), (weak.item_id, weak.text)])
    recommender = Recommender(ScoreWeights())

    def run() -> list[tuple[uuid.UUID, float]]:
        return [
            (item.item_id, item.score)
            for item in recommender.recommend(
                viewer(),
                [weak, strong],
                5,
                area_parents=PARENTS,
                skill_names=SKILL_NAMES,
                area_names=AREA_NAMES,
                index=index,
            )
        ]

    first = run()
    assert [item_id for item_id, _ in first] == [strong.item_id, weak.item_id]
    assert run() == first  # same inputs, same output, every time


def test_tfidf_top_terms_come_from_the_shared_vocabulary() -> None:
    item_id = uuid.uuid4()
    index = TfidfIndex.build(
        [
            (item_id, "soil moisture sensors calibration"),
            (uuid.uuid4(), "transformer language model"),
        ]
    )
    assert index is not None
    terms = index.top_terms("soil moisture sensing in farms", item_id)
    assert set(terms) <= {"soil", "moisture"}
    assert index.similarities("transformer language model")[item_id] == pytest.approx(0.0)


def test_cold_start_is_detected_from_a_sparse_profile() -> None:
    assert viewer(skills={}, research_areas=set(), text="  ").is_cold
    assert not viewer().is_cold


def test_offline_evaluation_stays_above_the_recorded_baseline() -> None:
    """Guards docs/ai-evaluation.md: a scoring change that degrades quality
    below the recorded numbers fails here."""
    results = evaluate(load_fixture())
    assert results["mean_precision_at_5"] >= 0.70
    assert results["mean_ndcg_at_10"] >= 0.95
