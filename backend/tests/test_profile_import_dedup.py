"""The de-duplication fixture set.

A curated set of records with known duplicates and name variants, which is
what the brief asks for: the merge rules are the part of this feature that
silently loses or duplicates a researcher's work if they are wrong, and they
are pure functions, so they get tested directly rather than through HTTP.

Every case here is a real pattern seen in the wild, noted beside it.
"""

from __future__ import annotations

import pytest

from app.modules.imports.connectors.base import ExternalWork, normalise_doi
from app.modules.imports.connectors.orcid import normalise_orcid
from app.modules.imports.merge import (
    merge_works,
    normalise_title,
    title_similarity,
)
from app.modules.imports.service import _pub_type


def work(
    source: str,
    title: str,
    *,
    doi: str | None = None,
    abstract: str | None = None,
    venue: str | None = None,
    year: int | None = None,
    pub_type: str | None = None,
    authors: tuple[str, ...] = (),
) -> ExternalWork:
    return ExternalWork(
        source=source,
        title=title,
        doi=doi,
        abstract=abstract,
        venue=venue,
        year=year,
        pub_type=pub_type,
        authors=authors,
    )


# ------------------------------------------------------------------- titles


@pytest.mark.parametrize(
    ("left", "right"),
    [
        # Typographic dash vs hyphen, and a colon the other source dropped.
        ("Bose–Einstein Condensation: A Review", "Bose-Einstein condensation - a review"),
        # Accents folded.
        ("Schrödinger's Equation Revisited", "Schrodingers equation revisited"),
        # One source carries the subtitle, the other does not.
        ("Deep learning for graphs", "Deep learning for graphs: a survey"),
        # Trailing punctuation and case.
        ("A Study of Psychoceramics.", "a study of psychoceramics"),
    ],
)
def test_same_paper_titles_score_as_duplicates(left: str, right: str) -> None:
    assert title_similarity(left, right) >= 92.0


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Deep learning for graphs", "Quantum error correction codes"),
        ("A study of rice yields in Punjab", "A study of wheat yields in Haryana"),
    ],
)
def test_different_papers_do_not_score_as_duplicates(left: str, right: str) -> None:
    assert title_similarity(left, right) < 84.0


def test_normalise_title_strips_punctuation_accents_and_case() -> None:
    assert normalise_title("Bose–Einstein Condensation: A Review!") == (
        "bose einstein condensation a review"
    )


# -------------------------------------------------------------------- merge


def test_records_sharing_a_doi_merge_into_one_work() -> None:
    merged = merge_works(
        [
            work("orcid", "Deep Learning for Graphs", doi="10.1/abc", year=2021),
            work(
                "crossref",
                "Deep learning for graphs: a survey",
                doi="10.1/abc",
                venue="IEEE TNN",
                year=2021,
                pub_type="journal-article",
                authors=("A Rao", "B Singh"),
            ),
            work(
                "semantic_scholar",
                "Deep learning for graphs",
                doi="10.1/abc",
                abstract="We survey graph neural networks.",
            ),
        ]
    )
    assert len(merged) == 1
    only = merged[0]
    # Crossref wins the bibliographic fields; Semantic Scholar wins the abstract.
    assert only.title == "Deep learning for graphs: a survey"
    assert only.venue == "IEEE TNN"
    assert only.authors == ("A Rao", "B Singh")
    assert only.abstract == "We survey graph neural networks."
    assert set(only.sources) == {"orcid", "crossref", "semantic_scholar"}


def test_different_dois_stay_separate_even_when_titles_match() -> None:
    """An erratum, a preprint and its version of record are distinct works.

    This is the case that a title-only rule gets wrong, and getting it wrong
    silently deletes a real publication from someone's record.
    """
    merged = merge_works(
        [
            work("crossref", "Deep learning for graphs", doi="10.1/abc", year=2021),
            work("crossref", "Deep learning for graphs", doi="10.1/err", year=2022),
        ]
    )
    assert len(merged) == 2
    assert {m.doi for m in merged} == {"10.1/abc", "10.1/err"}


def test_records_without_a_doi_merge_on_title() -> None:
    merged = merge_works(
        [
            work("openalex", "A Thesis on Psychoceramics", year=2019),
            work("orcid", "A thesis on psychoceramics!", year=2019),
        ]
    )
    assert len(merged) == 1
    assert set(merged[0].sources) == {"openalex", "orcid"}


def test_a_record_with_a_doi_never_merges_into_one_with_a_different_doi() -> None:
    merged = merge_works(
        [
            work("orcid", "Graph methods", doi="10.1/one"),
            work("openalex", "Graph methods", doi="10.1/two"),
            work("crossref", "Graph methods"),
        ]
    )
    # The DOI-less record joins one of them; the two DOIs stay apart.
    assert len({m.doi for m in merged if m.doi}) == 2


def test_merged_works_are_ordered_newest_first() -> None:
    merged = merge_works(
        [
            work("orcid", "Old paper", doi="10.1/a", year=2001),
            work("orcid", "New paper", doi="10.1/b", year=2024),
            work("orcid", "Middle paper", doi="10.1/c", year=2015),
        ]
    )
    assert [m.year for m in merged] == [2024, 2015, 2001]


# --------------------------------------------------------------- normalising


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0000-0002-1825-0097", "0000-0002-1825-0097"),
        ("https://orcid.org/0000-0002-1825-0097", "0000-0002-1825-0097"),
        ("http://orcid.org/0000-0002-1825-0097/", "0000-0002-1825-0097"),
        ("  0000-0002-1825-009X  ", "0000-0002-1825-009X"),
        ("0000-0002-1825-009x", "0000-0002-1825-009X"),
    ],
)
def test_orcid_is_accepted_in_every_form_people_paste(raw: str, expected: str) -> None:
    assert normalise_orcid(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "not-an-orcid", "0000-0002-1825", "0000-0002-1825-00977", "1234"]
)
def test_rubbish_is_not_accepted_as_an_orcid(raw: str) -> None:
    assert normalise_orcid(raw) is None


# ------------------------------------------------------------------- types


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("journal-article", "journal_article"),
        ("article", "journal_article"),
        ("proceedings-article", "conference_paper"),
        ("book-chapter", "book_chapter"),
        ("posted-content", "preprint"),
        ("dissertation", "thesis"),
        ("something-unheard-of", "other"),
        (None, "other"),
    ],
)
def test_external_publication_types_map_onto_the_register(raw: str | None, expected: str) -> None:
    assert _pub_type(raw).value == expected


# ---------------------------------------------------------------------- DOIs


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.1038/nature12373", "10.1038/nature12373"),
        # Case is not significant in a DOI, so they are stored lower-cased.
        ("10.1038/NATURE12373", "10.1038/nature12373"),
        ("https://doi.org/10.7717/peerj.175", "10.7717/peerj.175"),
        ("http://dx.doi.org/10.7717/peerj.175", "10.7717/peerj.175"),
        ("doi:10.7717/peerj.175", "10.7717/peerj.175"),
        # The one that broke a live import: OpenAlex percent-encodes the slash
        # on some records, and Crossref rejects the batch it appears in.
        ("https://doi.org/10.5210%2Fdisco.v5i0.2785", "10.5210/disco.v5i0.2785"),
        ("10.5210%2fdisco.v5i0.2785", "10.5210/disco.v5i0.2785"),
        ("  10.1234/X.Y  ", "10.1234/x.y"),
    ],
)
def test_dois_are_normalised_to_one_form(raw: str, expected: str) -> None:
    assert normalise_doi(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not-a-doi",
        # Prefix must be four or more digits; Crossref refuses anything else.
        "10.1/abc",
        "10.1234/",
        "https://example.com/paper",
        None,
    ],
)
def test_malformed_dois_are_dropped_rather_than_stored(raw: str | None) -> None:
    assert normalise_doi(raw) is None
