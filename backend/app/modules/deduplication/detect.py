"""Finding publications that may be the same work.

Deliberately reuses the importer's matching functions rather than growing a
second opinion about what makes two records the same paper. The thresholds
differ, and that difference is the whole point:

* `TITLE_MATCH_THRESHOLD` (92) is what the importer merges on, unattended.
* `TITLE_SUGGEST_THRESHOLD` (84) is what this *suggests* to a person.

The band between them is where a machine should not decide alone -- close
enough to be worth a look, not close enough to act on. Anything the importer
would merge outright never reaches the queue, because it was merged on the way
in.

The hard rule from `docs/publication-deduplication.md` holds here too: two
different DOIs are never the same work, however alike the titles. An erratum,
a preprint and its version of record are separate records on purpose, so such
a pair is not even offered.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.modules.imports.merge import (
    TITLE_SUGGEST_THRESHOLD,
    normalise_title,
    substitutes_a_word,
    title_similarity,
)


@dataclass(frozen=True, slots=True)
class Candidate:
    """One suspected pair, ordered so (a, b) and (b, a) are the same pair."""

    publication_a_id: uuid.UUID
    publication_b_id: uuid.UUID
    score: float
    evidence: dict[str, object]


@dataclass(frozen=True, slots=True)
class Record:
    """The little a publication needs to expose to be compared."""

    id: uuid.UUID
    title: str
    doi: str | None
    year: int | None
    venue: str | None
    author_names: frozenset[str]


def _author_overlap(left: Record, right: Record) -> list[str]:
    return sorted(left.author_names & right.author_names)


def find_candidates(records: Sequence[Record]) -> list[Candidate]:
    """Compare every record with every other. Pure, and O(n^2).

    Kept because it is the readable statement of the rules and the thing the
    rule tests exercise, but the scan does NOT use it: see
    `score_pairs`, which scores a shortlist the database produced.
    """
    pairs = [(left, right) for index, left in enumerate(records) for right in records[index + 1 :]]
    return score_pairs(pairs)


def score_pairs(pairs: Iterable[tuple[Record, Record]]) -> list[Candidate]:
    """Score an already-shortlisted set of pairs, strongest first.

    The split matters. Postgres generates the candidates with the trigram
    index (`title % title`), and rapidfuzz scores only what comes back --
    which is what the brief asks for, and what the import path has always
    done. Comparing every publication with every other in Python gets the
    same answer and stops being free the moment the register is large.
    """
    candidates = [
        candidate for left, right in pairs if (candidate := compare(left, right)) is not None
    ]
    # Strongest first: a reviewer working down the list meets the clearest
    # cases while their eye is still fresh.
    candidates.sort(key=lambda c: -c.score)
    return candidates


def compare(left: Record, right: Record) -> Candidate | None:
    # Different DOIs are different works. Not a score, a veto.
    if left.doi and right.doi and left.doi.lower() != right.doi.lower():
        return None

    score = title_similarity(left.title, right.title)
    if score < TITLE_SUGGEST_THRESHOLD:
        return None
    # A replaced word is a different study: "wheat" against "maize" scores
    # high on a token-set ratio and means something else entirely.
    if substitutes_a_word(left.title, right.title):
        return None

    shared_authors = _author_overlap(left, right)
    # Order the pair by id, which is what makes the unique constraint able to
    # say "this pair is already on the queue".
    first, second = (left, right) if left.id < right.id else (right, left)
    return Candidate(
        publication_a_id=first.id,
        publication_b_id=second.id,
        score=score,
        evidence={
            "title_similarity": round(score, 1),
            "identical_normalised_title": normalise_title(left.title)
            == normalise_title(right.title),
            "same_year": left.year == right.year and left.year is not None,
            "years": [left.year, right.year],
            "shared_doi": bool(left.doi and right.doi),
            "doi_on_one_side_only": bool(left.doi) != bool(right.doi),
            "same_venue": _same_venue(left.venue, right.venue),
            "shared_authors": shared_authors,
            "shared_author_count": len(shared_authors),
        },
    )


def _same_venue(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return normalise_title(left) == normalise_title(right)


__all__ = ["Candidate", "Record", "compare", "find_candidates", "score_pairs"]
