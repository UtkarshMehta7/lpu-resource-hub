"""Semantic Scholar connector -- abstracts and subject labels, keyed by DOI.

Deliberately NOT a profile source. Its Graph API has no ORCID route for
authors (`/author/ORCID:...` answers 404 -- verified, not assumed), so
identifying a person there would mean matching on name, and namesakes would
silently attach a stranger's papers to a researcher. ORCID and OpenAlex
already resolve identity properly.

What it is good for is the per-paper detail the other sources lack: an
abstract for almost everything, and `fieldsOfStudy` labels that feed the
skill and research-area suggestions. Those are looked up by DOI, which is
exact, so there is no guessing left in it.

Keyless callers share a rate-limited pool, so every failure here degrades to
"this source added nothing" rather than failing the import.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final

import httpx

from app.modules.imports.connectors.base import ExternalWork, clean, normalise_doi

BASE_URL: Final = "https://api.semanticscholar.org/graph/v1"

# The batch endpoint accepts up to 500 ids; 100 keeps each request quick and
# each failure small.
DOI_BATCH: Final = 100

_FIELDS: Final = "title,abstract,year,venue,publicationTypes,fieldsOfStudy,externalIds,url"


class SemanticScholarConnector:
    name = "semantic_scholar"
    label = "Semantic Scholar"

    def enrich(self, client: httpx.Client, dois: Iterable[str]) -> dict[str, ExternalWork]:
        wanted = [doi for doi in dict.fromkeys(normalise_doi(d) for d in dois) if doi]
        found: dict[str, ExternalWork] = {}
        for start in range(0, len(wanted), DOI_BATCH):
            batch = wanted[start : start + DOI_BATCH]
            for doi, row in zip(batch, self._batch(client, batch), strict=False):
                # An unknown DOI comes back as a null in the same position.
                if not isinstance(row, Mapping):
                    continue
                work = _to_work(doi, row)
                if work:
                    found[doi] = work
        return found

    def _batch(self, client: httpx.Client, dois: list[str]) -> list[Any]:
        try:
            response = client.post(
                f"{BASE_URL}/paper/batch",
                params={"fields": _FIELDS},
                json={"ids": [f"DOI:{doi}" for doi in dois]},
            )
        except httpx.HTTPError:
            return []
        if response.status_code != httpx.codes.OK:
            return []
        payload = response.json()
        return payload if isinstance(payload, list) else []


def _to_work(doi: str, row: Mapping[str, Any]) -> ExternalWork | None:
    title = clean(row.get("title"), limit=500)
    if not title:
        return None
    types = row.get("publicationTypes")
    return ExternalWork(
        source="semantic_scholar",
        title=title,
        doi=doi,
        abstract=clean(row.get("abstract"), limit=5000),
        venue=clean(row.get("venue"), limit=300),
        year=row.get("year") if isinstance(row.get("year"), int) else None,
        pub_type=clean(types[0]) if isinstance(types, list) and types else None,
        url=clean(row.get("url")),
    )


__all__ = ["SemanticScholarConnector"]
