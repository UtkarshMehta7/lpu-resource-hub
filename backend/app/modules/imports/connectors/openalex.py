"""OpenAlex connector.

OpenAlex is what this project uses instead of Scopus. It is CC0, needs no key
and indexes roughly the same corpus, so it supplies the breadth the brief
wanted from Scopus -- affiliations, subject topics and citation metrics --
without the paid institutional licence that the zero-cost rule forbids.

Two traps, both found by testing rather than by reading the docs:

1. Filtering authors by an ORCID that OpenAlex does not hold does NOT return
   zero results. It falls back to fuzzy matching and cheerfully returns other
   people -- a lookup of ORCID's own demo iD came back with 42 strangers. So
   every ORCID hit is re-checked against the `orcid` field on the way out.
2. Abstracts are stored as an inverted index (word -> positions), not as
   text, so they have to be rebuilt.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import httpx
from rapidfuzz import fuzz

from app.modules.imports.connectors.base import (
    AuthorCandidate,
    ConnectorError,
    ExternalProfile,
    ExternalWork,
    ProfileQuery,
    clean,
    normalise_doi,
)

BASE_URL: Final = "https://api.openalex.org"

# OpenAlex pages at 200 max. Nobody's import needs more than this, and an
# unbounded fetch would be a slow request the user is waiting on.
WORKS_PER_PAGE: Final = 200
MAX_WORKS: Final = 200

# How close a name has to be (0-100) to break a tie between author records
# sharing one ORCID. Deliberately high: a wrong tie-break attributes a
# stranger's whole publication list to the wrong researcher.
NAME_MATCH_THRESHOLD: Final = 90.0


class OpenAlexConnector:
    name = "openalex"
    label = "OpenAlex"

    def __init__(self, contact_email: str) -> None:
        # OpenAlex routes identified callers into a faster pool; anonymous
        # callers share a slower one and get throttled first.
        self._mailto = contact_email

    def fetch(self, client: httpx.Client, query: ProfileQuery) -> ExternalProfile | None:
        author = self._find_author(client, query)
        if author is None:
            return None

        author_id = clean(author.get("id"))
        if not author_id:
            return None

        stats = author.get("summary_stats")
        metrics: dict[str, int] = {}
        for key, source in (
            ("works_count", author.get("works_count")),
            ("cited_by_count", author.get("cited_by_count")),
            ("h_index", stats.get("h_index") if isinstance(stats, Mapping) else None),
        ):
            if isinstance(source, int):
                metrics[key] = source

        return ExternalProfile(
            source=self.name,
            source_id=author_id.rsplit("/", 1)[-1],
            source_url=author_id,
            full_name=clean(author.get("display_name"), limit=200),
            affiliation=_affiliation(author),
            topics=_topics(author),
            metrics=metrics,
            works=self._works(client, author_id),
        )

    # ------------------------------------------------------------------ lookup

    def _find_author(self, client: httpx.Client, query: ProfileQuery) -> Mapping[str, Any] | None:
        # A person who picked themselves off a list is the best evidence
        # there is, so it is checked before anything is inferred.
        if query.openalex_author_id:
            return self._by_id(client, query.openalex_author_id)
        if query.orcid:
            author = self._by_orcid(client, query.orcid, query.name)
            if author is not None:
                return author
        if query.name:
            return self._by_name(client, query.name, query.affiliation)
        return None

    def _by_orcid(
        self, client: httpx.Client, orcid: str, name: str | None
    ) -> Mapping[str, Any] | None:
        """Resolve an ORCID to exactly one OpenAlex author, or refuse.

        An ORCID is supposed to identify one person, but OpenAlex holds
        whatever the papers claimed. ORCID's own public demo iD resolves to 42
        different author records here, because real people pasted the example
        into their submissions. So a single exact match is trusted, several
        matches are an ambiguity to be resolved by name -- and if it cannot be
        resolved, nothing is returned. Importing a stranger's publications
        under someone's name is far worse than importing none.
        """
        results = self._get(client, "/authors", {"filter": f"orcid:{orcid}", "per-page": "50"})
        wanted = orcid.strip().rsplit("/", 1)[-1].upper()
        exact = [
            author
            for author in results
            if (clean(author.get("orcid")) or "").rsplit("/", 1)[-1].upper() == wanted
        ]
        if not exact:
            return None
        if len(exact) == 1:
            return exact[0]

        if name:
            best, score = _closest_by_name(exact, name)
            if best is not None and score >= NAME_MATCH_THRESHOLD:
                return best
        raise ConnectorError(
            f"OpenAlex holds {len(exact)} different author records for that ORCID iD, "
            "so it cannot tell which one is you. The other sources were still used."
        )

    def _by_id(self, client: httpx.Client, author_id: str) -> Mapping[str, Any] | None:
        """Fetch one author the researcher chose explicitly."""
        short = author_id.rsplit("/", 1)[-1]
        rows = self._get(client, "/authors", {"filter": f"openalex:{short}", "per-page": "1"})
        return rows[0] if rows else None

    def _by_name(
        self, client: httpx.Client, name: str, affiliation: str | None
    ) -> Mapping[str, Any] | None:
        """The single best name match, or nothing.

        Used only when the caller did not pick a candidate. An affiliation
        that matches is good evidence; without one this refuses to guess,
        because a name alone is how somebody ends up importing a stranger's
        publication list. The caller is expected to offer
        `search_candidates` instead.
        """
        results = self._get(client, "/authors", {"search": name, "per-page": "25"})
        if not results:
            return None
        if affiliation:
            needle = affiliation.casefold()
            for author in results:
                place = (_affiliation(author) or "").casefold()
                if needle and (needle in place or place in needle):
                    return author
        if len(results) == 1:
            return results[0]
        raise ConnectorError(
            f"{len(results)} researchers on OpenAlex match that name. Choose which one is you."
        )

    def search_candidates(
        self, client: httpx.Client, name: str, affiliation: str | None, *, limit: int = 10
    ) -> list[AuthorCandidate]:
        """People who might be the one searching, best match first.

        Returned instead of a guess: the point is that the researcher picks,
        having seen where each one works and what they publish on.
        """
        results = self._get(client, "/authors", {"search": name, "per-page": str(limit * 2)})
        candidates: list[AuthorCandidate] = []
        for author in results:
            identifier = clean(author.get("id"))
            display = clean(author.get("display_name"), limit=200)
            if not identifier or not display:
                continue
            stats = author.get("summary_stats")
            orcid = clean(author.get("orcid"))
            candidates.append(
                AuthorCandidate(
                    source=self.name,
                    source_id=identifier.rsplit("/", 1)[-1],
                    source_url=identifier,
                    full_name=display,
                    affiliation=_affiliation(author),
                    other_affiliations=_all_affiliations(author)[:3],
                    orcid=orcid.rsplit("/", 1)[-1] if orcid else None,
                    works_count=(
                        author.get("works_count")
                        if isinstance(author.get("works_count"), int)
                        else None
                    ),
                    cited_by_count=(
                        author.get("cited_by_count")
                        if isinstance(author.get("cited_by_count"), int)
                        else None
                    ),
                    h_index=(
                        stats.get("h_index")
                        if isinstance(stats, Mapping) and isinstance(stats.get("h_index"), int)
                        else None
                    ),
                    topics=_topics(author)[:4],
                )
            )
        if affiliation:
            needle = affiliation.casefold()
            candidates.sort(key=lambda c: needle not in (c.affiliation or "").casefold())
        return candidates[:limit]

    def _works(self, client: httpx.Client, author_id: str) -> tuple[ExternalWork, ...]:
        rows = self._get(
            client,
            "/works",
            {
                "filter": f"author.id:{author_id.rsplit('/', 1)[-1]}",
                "per-page": str(WORKS_PER_PAGE),
                "sort": "publication_year:desc",
            },
        )
        works: list[ExternalWork] = []
        for row in rows[:MAX_WORKS]:
            title = clean(row.get("display_name") or row.get("title"), limit=500)
            if not title:
                continue
            works.append(
                ExternalWork(
                    source=self.name,
                    title=title,
                    doi=normalise_doi(row.get("doi")),
                    abstract=_abstract(row.get("abstract_inverted_index")),
                    venue=_venue(row),
                    year=row.get("publication_year")
                    if isinstance(row.get("publication_year"), int)
                    else None,
                    pub_type=clean(row.get("type")),
                    url=clean(row.get("doi")) or clean(row.get("id")),
                    authors=_authors(row),
                )
            )
        return tuple(works)

    # ------------------------------------------------------------------- http

    def _get(
        self, client: httpx.Client, path: str, params: dict[str, str]
    ) -> list[Mapping[str, Any]]:
        try:
            response = client.get(f"{BASE_URL}{path}", params={**params, "mailto": self._mailto})
        except httpx.HTTPError as exc:
            raise ConnectorError(f"OpenAlex could not be reached: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise ConnectorError(f"OpenAlex answered {response.status_code}.")
        payload = response.json()
        results = payload.get("results") if isinstance(payload, Mapping) else None
        if not isinstance(results, list):
            return []
        return [row for row in results if isinstance(row, Mapping)]


# --------------------------------------------------------------------- fields


def _affiliation(author: Mapping[str, Any]) -> str | None:
    known = author.get("last_known_institutions")
    if isinstance(known, list):
        for institution in known:
            name = (
                clean(institution.get("display_name")) if isinstance(institution, Mapping) else None
            )
            if name:
                return name[:200]
    affiliations = author.get("affiliations")
    if isinstance(affiliations, list):
        for entry in affiliations:
            institution = entry.get("institution") if isinstance(entry, Mapping) else None
            name = (
                clean(institution.get("display_name")) if isinstance(institution, Mapping) else None
            )
            if name:
                return name[:200]
    return None


def _closest_by_name(
    authors: list[Mapping[str, Any]], name: str
) -> tuple[Mapping[str, Any] | None, float]:
    best: Mapping[str, Any] | None = None
    best_score = 0.0
    for author in authors:
        candidate = clean(author.get("display_name"))
        if not candidate:
            continue
        score = fuzz.token_sort_ratio(name.casefold(), candidate.casefold())
        if score > best_score:
            best, best_score = author, score
    return best, best_score


def _all_affiliations(author: Mapping[str, Any]) -> tuple[str, ...]:
    """Every institution OpenAlex associates with them, most recent first."""
    found: list[str] = []
    for key in ("last_known_institutions", "affiliations"):
        entries = author.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            institution = (
                entry.get("institution")
                if isinstance(entry, Mapping) and "institution" in entry
                else entry
            )
            name = (
                clean(institution.get("display_name"), limit=200)
                if isinstance(institution, Mapping)
                else None
            )
            if name and name not in found:
                found.append(name)
    return tuple(found)


def _topics(author: Mapping[str, Any]) -> tuple[str, ...]:
    found: list[str] = []
    topics = author.get("topics")
    if isinstance(topics, list):
        for topic in topics:
            name = (
                clean(topic.get("display_name"), limit=100) if isinstance(topic, Mapping) else None
            )
            if name:
                found.append(name)
    return tuple(dict.fromkeys(found))


def _venue(row: Mapping[str, Any]) -> str | None:
    location = row.get("primary_location")
    source = location.get("source") if isinstance(location, Mapping) else None
    if isinstance(source, Mapping):
        return clean(source.get("display_name"), limit=300)
    return None


def _authors(row: Mapping[str, Any]) -> tuple[str, ...]:
    names: list[str] = []
    authorships = row.get("authorships")
    if isinstance(authorships, list):
        for authorship in authorships:
            author = authorship.get("author") if isinstance(authorship, Mapping) else None
            name = (
                clean(author.get("display_name"), limit=200)
                if isinstance(author, Mapping)
                else None
            )
            if name:
                names.append(name)
    return tuple(names)


def _abstract(inverted: object) -> str | None:
    """Rebuild text from OpenAlex's {word: [positions]} inverted index."""
    if not isinstance(inverted, Mapping) or not inverted:
        return None
    slots: dict[int, str] = {}
    for word, positions in inverted.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int):
                slots[position] = word
    if not slots:
        return None
    return clean(" ".join(slots[i] for i in sorted(slots)), limit=5000)


__all__ = ["OpenAlexConnector"]
