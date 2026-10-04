"""The suggestion rules, as a table. No database.

`find_candidates` is a pure function over records, so the rules can be stated
as cases rather than discovered through the API. The band between the two
thresholds is the point of the whole feature:

    84 ----------------- suggest to a person ----------------- 92 -- merge

Below 84, nothing. Above 92, the importer already merged it unattended on the
way in, so it never reaches a reviewer.
"""

from __future__ import annotations

import uuid

import pytest

from app.modules.deduplication.detect import Record, find_candidates
from app.modules.imports.merge import TITLE_MATCH_THRESHOLD, TITLE_SUGGEST_THRESHOLD


def record(
    title: str,
    *,
    doi: str | None = None,
    year: int | None = 2024,
    venue: str | None = "Journal of Agritech",
    authors: tuple[str, ...] = ("a singh",),
) -> Record:
    return Record(
        id=uuid.uuid4(),
        title=title,
        doi=doi,
        year=year,
        venue=venue,
        author_names=frozenset(authors),
    )


def test_the_suggest_band_sits_below_the_merge_threshold() -> None:
    """If these ever cross, the queue would offer what the importer already
    merged, or nothing at all."""
    assert TITLE_SUGGEST_THRESHOLD < TITLE_MATCH_THRESHOLD


def test_identical_titles_are_suggested() -> None:
    pairs = find_candidates([record("Soil moisture sensing"), record("Soil moisture sensing")])

    assert len(pairs) == 1
    assert pairs[0].score == 100.0
    assert pairs[0].evidence["identical_normalised_title"] is True


def test_punctuation_and_case_do_not_separate_a_pair() -> None:
    pairs = find_candidates(
        [
            record("Bose--Einstein Condensation: A Review"),
            record("bose-einstein condensation - a review"),
        ]
    )

    assert len(pairs) == 1


def test_unrelated_titles_are_not_suggested() -> None:
    pairs = find_candidates(
        [record("Soil moisture sensing"), record("Quantum error correction codes")]
    )

    assert pairs == []


def test_two_different_dois_are_vetoed_however_alike_the_titles() -> None:
    """Not a score adjustment -- a veto. An erratum and its article, or a
    preprint and its version of record, are separate works."""
    pairs = find_candidates(
        [
            record("Bose-Einstein condensation", doi="10.1000/aaa"),
            record("Bose-Einstein condensation", doi="10.1000/bbb"),
        ]
    )

    assert pairs == []


def test_the_same_doi_in_different_case_is_not_a_veto() -> None:
    pairs = find_candidates(
        [
            record("Bose-Einstein condensation", doi="10.1000/ABC"),
            record("Bose-Einstein condensation", doi="10.1000/abc"),
        ]
    )

    assert len(pairs) == 1
    assert pairs[0].evidence["shared_doi"] is True


def test_a_substituted_word_is_a_different_study() -> None:
    pairs = find_candidates(
        [
            record("Forecasting wheat yield from open satellite data"),
            record("Forecasting maize yield from open satellite data"),
        ]
    )

    assert pairs == []


def test_a_dropped_subtitle_is_the_same_work() -> None:
    pairs = find_candidates(
        [
            record("Forecasting wheat yield"),
            record("Forecasting wheat yield from open satellite data"),
        ]
    )

    assert len(pairs) == 1


def test_evidence_reports_a_doi_on_one_side_only() -> None:
    """The commonest real duplicate: somebody typed the paper in, and an
    import later brought the same paper with its DOI."""
    pairs = find_candidates(
        [
            record("Drip irrigation uptake"),
            record("Drip irrigation uptake", doi="10.1000/drip"),
        ]
    )

    assert pairs[0].evidence["doi_on_one_side_only"] is True
    assert pairs[0].evidence["shared_doi"] is False


def test_evidence_counts_shared_authors_and_notes_the_years() -> None:
    pairs = find_candidates(
        [
            record("Canal seepage", year=2023, authors=("a singh", "b kaur")),
            record("Canal seepage", year=2024, authors=("b kaur", "c gill")),
        ]
    )

    evidence = pairs[0].evidence
    assert evidence["shared_authors"] == ["b kaur"]
    assert evidence["shared_author_count"] == 1
    assert evidence["same_year"] is False
    assert evidence["years"] == [2023, 2024]


def test_a_pair_is_ordered_by_id_so_it_cannot_be_queued_twice() -> None:
    """The unique constraint can only say "already on the queue" if the pair
    always arrives the same way round."""
    left, right = record("Fodder quality"), record("Fodder quality")

    forwards = find_candidates([left, right])
    backwards = find_candidates([right, left])

    assert (forwards[0].publication_a_id, forwards[0].publication_b_id) == (
        backwards[0].publication_a_id,
        backwards[0].publication_b_id,
    )
    assert forwards[0].publication_a_id < forwards[0].publication_b_id


def test_strongest_matches_come_first() -> None:
    pairs = find_candidates(
        [
            record("Groundwater depletion in the Doab"),
            record("Groundwater depletion in the Doab"),
            record("Groundwater depletion in the Doab region of Punjab"),
        ]
    )

    assert len(pairs) == 3
    assert pairs == sorted(pairs, key=lambda c: -c.score)


@pytest.mark.parametrize("count", [0, 1])
def test_fewer_than_two_records_yield_nothing(count: int) -> None:
    assert find_candidates([record("Only one") for _ in range(count)]) == []
