"""Merging and de-duplicating what the sources returned.

Four sites describe the same researcher and the same papers in four different
ways. This module reduces that to one candidate list, before anything touches
the database.

The de-duplication rule, in order:

1. **DOI, exact.** A DOI is an identifier, so two records sharing one are the
   same work, full stop. No scoring, no threshold.
2. **Normalised title, fuzzy.** Records without a DOI (books, theses, older
   conference papers) fall back to a normalised title compared with
   rapidfuzz's token-set ratio, which is insensitive to word order and to one
   source carrying a subtitle the other dropped.

Field-level precedence, once records are grouped: Crossref wins on the
bibliographic fields because it returns what the publisher registered;
Semantic Scholar wins on abstracts because it has them for almost everything;
ORCID wins on nothing except the fact that the researcher claimed the work.
The known failure cases are written up in docs/publication-deduplication.md.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from rapidfuzz import fuzz

from app.modules.imports.connectors.base import ExternalProfile, ExternalWork

# Two titles at or above this are treated as the same work. Chosen high: the
# cost of a false merge (losing a real publication) is worse than the cost of
# a false split (a duplicate the researcher unticks in the review step).
TITLE_MATCH_THRESHOLD: Final = 92.0

# Below this, two titles are not even shown as a possible duplicate.
TITLE_SUGGEST_THRESHOLD: Final = 84.0

# Which source to believe for each field, best first.
_METADATA_ORDER: Final = ("crossref", "openalex", "semantic_scholar", "orcid")
_ABSTRACT_ORDER: Final = ("semantic_scholar", "crossref", "openalex", "orcid")

_PUNCTUATION: Final = re.compile(r"[^\w\s]+", re.UNICODE)
_WHITESPACE: Final = re.compile(r"\s+")


def normalise_title(title: str) -> str:
    """Strip a title down to what two records would share if they matched.

    Accents are folded, punctuation dropped and whitespace collapsed, because
    "Bose--Einstein Condensation: A Review" and "Bose-Einstein condensation - a
    review" are the same paper and must normalise to the same string.
    """
    decomposed = unicodedata.normalize("NFKD", title)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = without_marks.casefold()
    stripped = _PUNCTUATION.sub(" ", lowered)
    return _WHITESPACE.sub(" ", stripped).strip()


def title_similarity(left: str, right: str) -> float:
    """0-100. Token-set ratio, so word order and a dropped subtitle are fine."""
    return float(fuzz.token_set_ratio(normalise_title(left), normalise_title(right)))


@dataclass(frozen=True, slots=True)
class MergedWork:
    """One work, assembled from every source that described it."""

    title: str
    doi: str | None
    abstract: str | None
    venue: str | None
    year: int | None
    pub_type: str | None
    url: str | None
    authors: tuple[str, ...]
    sources: tuple[str, ...]

    @property
    def key(self) -> str:
        return f"doi:{self.doi}" if self.doi else f"title:{normalise_title(self.title)}"


def merge_works(works: Iterable[ExternalWork]) -> list[MergedWork]:
    """Group records describing the same work and fold each group into one."""
    groups: list[list[ExternalWork]] = []
    by_doi: dict[str, int] = {}

    for work in works:
        index = _find_group(work, groups, by_doi)
        if index is None:
            groups.append([work])
            index = len(groups) - 1
        else:
            groups[index].append(work)
        if work.doi:
            by_doi.setdefault(work.doi, index)

    merged = [_fold(group) for group in groups]
    # Newest first, untitled/undated last -- the order a researcher expects.
    merged.sort(key=lambda w: (-(w.year or 0), w.title.casefold()))
    return merged


def _find_group(
    work: ExternalWork, groups: Sequence[Sequence[ExternalWork]], by_doi: Mapping[str, int]
) -> int | None:
    # Rule 1: a shared DOI is decisive.
    if work.doi is not None:
        existing = by_doi.get(work.doi)
        if existing is not None:
            return existing
    # Rule 2: fall back to the title, but never merge across two records that
    # both carry a DOI and disagree -- different DOIs mean different works,
    # however similar the titles (an erratum, a preprint and its version of
    # record, a reprint).
    for index, group in enumerate(groups):
        for candidate in group:
            if work.doi and candidate.doi and work.doi != candidate.doi:
                continue
            if title_similarity(work.title, candidate.title) >= TITLE_MATCH_THRESHOLD:
                return index
    return None


def _fold(group: Sequence[ExternalWork]) -> MergedWork:
    def pick(field: str, order: Sequence[str] = _METADATA_ORDER) -> object:
        for source in order:
            for item in group:
                if item.source == source and getattr(item, field) is not None:
                    return getattr(item, field)
        for item in group:
            if getattr(item, field) is not None:
                return getattr(item, field)
        return None

    authors: tuple[str, ...] = ()
    for source in _METADATA_ORDER:
        for item in group:
            if item.source == source and item.authors:
                authors = item.authors
                break
        if authors:
            break

    title = pick("title")
    return MergedWork(
        title=str(title) if title is not None else group[0].title,
        doi=_as_str(pick("doi")),
        abstract=_as_str(pick("abstract", _ABSTRACT_ORDER)),
        venue=_as_str(pick("venue")),
        year=_as_int(pick("year")),
        pub_type=_as_str(pick("pub_type")),
        url=_as_str(pick("url")),
        authors=authors,
        sources=tuple(dict.fromkeys(item.source for item in group)),
    )


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_int(value: object) -> int | None:
    # bool is a subclass of int; a True year would be a data bug, not a date.
    return value if isinstance(value, int) and not isinstance(value, bool) else None


@dataclass(frozen=True, slots=True)
class MergedProfile:
    """The researcher, as the sources jointly describe them."""

    full_name: str | None
    designation: str | None
    affiliation: str | None
    bio: str | None
    links: tuple[tuple[str, str], ...]
    topics: tuple[str, ...]
    metrics: Mapping[str, int]
    works: tuple[MergedWork, ...]
    sources: tuple[str, ...]
    source_urls: Mapping[str, str]


# For the person's own details ORCID wins: they curate that record themselves,
# whereas OpenAlex infers affiliation from whatever the papers said.
_PROFILE_ORDER: Final = ("orcid", "openalex", "semantic_scholar", "crossref")


def merge_profiles(
    profiles: Sequence[ExternalProfile], works: Iterable[ExternalWork]
) -> MergedProfile:
    ordered = sorted(
        profiles,
        key=lambda p: _PROFILE_ORDER.index(p.source) if p.source in _PROFILE_ORDER else 99,
    )

    def first(field: str) -> str | None:
        for profile in ordered:
            value = getattr(profile, field)
            if isinstance(value, str) and value:
                return value
        return None

    links: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    for profile in ordered:
        for label, url in profile.links:
            if url not in seen_urls:
                seen_urls.add(url)
                links.append((label, url))

    topics: list[str] = []
    for profile in ordered:
        for topic in profile.topics:
            if topic not in topics:
                topics.append(topic)

    metrics: dict[str, int] = {}
    for profile in ordered:
        for key, value in profile.metrics.items():
            # Keep the highest figure any source reports rather than the first:
            # coverage differs, and the fuller count is the useful one.
            metrics[key] = max(metrics.get(key, 0), value)

    return MergedProfile(
        full_name=first("full_name"),
        designation=first("designation"),
        affiliation=first("affiliation"),
        bio=first("bio"),
        links=tuple(links),
        topics=tuple(topics),
        metrics=metrics,
        works=tuple(merge_works(works)),
        sources=tuple(dict.fromkeys(p.source for p in ordered)),
        source_urls={p.source: p.source_url for p in ordered if p.source_url},
    )


__all__ = [
    "MergedProfile",
    "MergedWork",
    "TITLE_MATCH_THRESHOLD",
    "TITLE_SUGGEST_THRESHOLD",
    "merge_profiles",
    "merge_works",
    "normalise_title",
    "title_similarity",
]
