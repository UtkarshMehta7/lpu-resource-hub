"""Crossref connector -- the metadata authority.

Crossref is not a profile site and is deliberately not used as one: it is
work-centric, and its author records are too thin to identify a person. Its
job here is to canonicalise. ORCID and OpenAlex both hand back DOIs, and
whatever they say the title or venue is, Crossref returns what the publisher
actually registered. That is the version worth storing.

Keyless, but `mailto` puts the caller in the faster "polite pool".
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final

import httpx

from app.modules.imports.connectors.base import (
    ConnectorError,
    ExternalWork,
    clean,
    normalise_doi,
)

BASE_URL: Final = "https://api.crossref.org"

# Crossref's own guidance is to keep a filter URL short; 40 DOIs per request
# stays well inside any sane URL limit while keeping the round trips few.
DOI_BATCH: Final = 40


class CrossrefConnector:
    name = "crossref"
    label = "Crossref"

    def __init__(self, contact_email: str) -> None:
        self._mailto = contact_email

    def enrich(self, client: httpx.Client, dois: Iterable[str]) -> dict[str, ExternalWork]:
        """Look up DOIs and return the publisher-registered metadata.

        Unknown DOIs are simply absent from the result. A failure here is
        never fatal: the caller keeps whatever ORCID and OpenAlex said.
        """
        wanted = [doi for doi in dict.fromkeys(normalise_doi(d) for d in dois) if doi]
        found: dict[str, ExternalWork] = {}
        for start in range(0, len(wanted), DOI_BATCH):
            self._collect(client, wanted[start : start + DOI_BATCH], found)
        return found

    def _collect(
        self, client: httpx.Client, batch: list[str], found: dict[str, ExternalWork]
    ) -> None:
        """Fetch one batch, halving it if Crossref rejects the whole request.

        Crossref validates every DOI in a filter and answers 400 for the batch
        if any single one offends, so one unusable identifier would otherwise
        cost the metadata for the 39 good ones beside it. Halving finds and
        isolates the offender in a handful of requests instead of refetching
        everything one at a time.
        """
        if not batch:
            return
        try:
            rows = self._query(client, batch)
        except ConnectorError:
            if len(batch) == 1:
                # A single DOI Crossref will not accept: nothing to salvage.
                return
            middle = len(batch) // 2
            self._collect(client, batch[:middle], found)
            self._collect(client, batch[middle:], found)
            return
        for row in rows:
            work = _to_work(row)
            if work and work.doi:
                found[work.doi] = work

    def _query(self, client: httpx.Client, dois: list[str]) -> list[Mapping[str, Any]]:
        params = {
            "filter": ",".join(f"doi:{doi}" for doi in dois),
            "rows": str(len(dois)),
            "mailto": self._mailto,
            "select": "DOI,title,container-title,issued,type,author,abstract,URL",
        }
        try:
            response = client.get(f"{BASE_URL}/works", params=params)
        except httpx.HTTPError as exc:
            raise ConnectorError(f"Crossref could not be reached: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise ConnectorError(f"Crossref answered {response.status_code}.")
        payload = response.json()
        items = payload.get("message", {}).get("items") if isinstance(payload, Mapping) else None
        if not isinstance(items, list):
            return []
        return [row for row in items if isinstance(row, Mapping)]


def _to_work(row: Mapping[str, Any]) -> ExternalWork | None:
    doi = normalise_doi(row.get("DOI"))
    title = _first(row.get("title"))
    if not doi or not title:
        return None
    return ExternalWork(
        source="crossref",
        title=title[:500],
        doi=doi,
        abstract=_abstract(row.get("abstract")),
        venue=_first(row.get("container-title")),
        year=_year(row.get("issued")),
        pub_type=clean(row.get("type")),
        url=clean(row.get("URL")),
        authors=_authors(row.get("author")),
    )


def _first(value: object) -> str | None:
    if isinstance(value, list):
        for item in value:
            cleaned = clean(item, limit=500)
            if cleaned:
                return cleaned
    return clean(value, limit=500)


def _abstract(value: object) -> str | None:
    """Crossref abstracts arrive as JATS XML; strip the tags."""
    text = clean(value, limit=20000)
    if not text:
        return None
    import re

    stripped = re.sub(r"<[^>]+>", " ", text)
    return clean(stripped, limit=5000)


def _year(issued: object) -> int | None:
    parts = issued.get("date-parts") if isinstance(issued, Mapping) else None
    if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
        candidate = parts[0][0]
        if isinstance(candidate, int) and 1500 <= candidate <= 2200:
            return candidate
    return None


def _authors(value: object) -> tuple[str, ...]:
    names: list[str] = []
    if not isinstance(value, list):
        return ()
    for entry in value:
        if not isinstance(entry, Mapping):
            continue
        given = clean(entry.get("given"))
        family = clean(entry.get("family"))
        joined = clean(" ".join(part for part in (given, family) if part)) or clean(
            entry.get("name")
        )
        if joined:
            names.append(joined[:200])
    return tuple(names)


__all__ = ["CrossrefConnector"]
