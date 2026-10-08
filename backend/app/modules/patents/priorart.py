"""Prior-art search for a patent that is about to be filed.

**This does not search the world's patents, and the interface must say so.**
Every open worldwide register was tested and none can be read without a key:

* EPO OPS (Espacenet) answers 403 without an OAuth credential.
* USPTO's Open Data API answers 401.
* PatentsView retired its keyless endpoint; both hosts now serve a web page
  where the JSON used to be.
* WIPO PATENTSCOPE answers 403 and publishes no API.
* PQAI, the open-source prior-art service, answers 401 without a token.

That is the same wall ADR 0025 hit with Scopus and Web of Science, and the
zero-cost rule answers it the same way: use what is open, and be explicit
about the edge of what was searched. Claiming novelty we have not checked
would be the single most harmful thing this feature could do.

So it does three honest things instead:

1. **Looks for the same invention already recorded here.** Two teams in one
   university filing over each other is the failure this can actually
   prevent, and it reuses the trigram shortlist and rapidfuzz scoring the
   publication de-duplication already runs on.
2. **Searches the open literature.** A published paper is prior art in
   exactly the way another patent is, and it is what most often destroys
   novelty. OpenAlex and Crossref are keyless and already wired up.
3. **Hands the query to the registers that can answer it**, pre-built, so
   the worldwide search happens where it is actually possible.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Final
from urllib.parse import quote_plus

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.imports.connectors.base import build_client
from app.modules.imports.merge import TITLE_SUGGEST_THRESHOLD, title_similarity
from app.modules.patents.models import Patent
from app.modules.patents.schemas import (
    PriorArtResult,
    RegistrySearch,
    RelatedWork,
    SimilarPatent,
)

#: How many of each kind to return. A prior-art panel is read before filing,
#: not audited afterwards, so a short ranked list beats an exhaustive one.
LIMIT: Final = 8

OPENALEX_URL: Final = "https://api.openalex.org/works"
CROSSREF_URL: Final = "https://api.crossref.org/works"

#: The two lookups run CONCURRENTLY and share this budget rather than queueing
#: through it. Crossref's `query.bibliographic` regularly takes more than ten
#: seconds, and the frontend's HTTP client gives the whole request ten -- so
#: sequential calls could never both fit, and the slow one always lost. Six
#: seconds each, in parallel, leaves room for the database work and the
#: response. A source that misses it is reported as unavailable, never
#: silently dropped.
SOURCE_TIMEOUT: Final = httpx.Timeout(6.0, connect=3.0)


def _registries(title: str) -> list[RegistrySearch]:
    """The registers that can answer the worldwide question, query pre-built."""
    q = quote_plus(title)
    return [
        RegistrySearch(
            name="Espacenet",
            description="The European Patent Office's worldwide collection, "
            "over 140 million documents.",
            url=f"https://worldwide.espacenet.com/patent/search?q={q}",
        ),
        RegistrySearch(
            name="Google Patents",
            description="Full text of patents from more than 100 offices, "
            "with machine translation.",
            url=f"https://patents.google.com/?q={q}",
        ),
        RegistrySearch(
            name="WIPO PATENTSCOPE",
            description="International PCT applications and 80-odd national collections.",
            url=f"https://patentscope.wipo.int/search/en/result.jsf?query={q}",
        ),
        RegistrySearch(
            name="InPASS (India)",
            description="The Indian Patent Office's own full-text search.",
            url="https://iprsearch.ipindia.gov.in/PublicSearch/",
        ),
    ]


def _similar_patents(db: Session, title: str, exclude_id: Any | None) -> list[SimilarPatent]:
    """Patents already recorded here whose title is close to this one.

    Postgres shortlists with the trigram index and rapidfuzz scores what comes
    back -- the same division of labour as the duplicate scan, and for the
    same reason: comparing everything with everything in Python gets the same
    answer and stops being free as the register grows.
    """
    query = select(Patent).where(text("patents.title % :probe")).params(probe=title)
    if exclude_id is not None:
        query = query.where(Patent.id != exclude_id)
    candidates = db.execute(query.limit(200)).scalars().all()

    scored = [
        (score, patent)
        for patent in candidates
        if (score := title_similarity(title, patent.title)) >= TITLE_SUGGEST_THRESHOLD
    ]
    scored.sort(key=lambda pair: -pair[0])
    return [
        SimilarPatent(
            id=patent.id,
            title=patent.title,
            jurisdiction=patent.jurisdiction,
            status=patent.status,
            filing_date=patent.filing_date,
            grant_number=patent.grant_number,
            score=round(score, 1),
        )
        for score, patent in scored[:LIMIT]
    ]


def _openalex(client: httpx.Client, query: str, mailto: str) -> list[RelatedWork]:
    response = client.get(
        OPENALEX_URL,
        params={"search": query, "per-page": str(LIMIT), "mailto": mailto},
    )
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results") if isinstance(payload, dict) else None
    works: list[RelatedWork] = []
    for row in results or []:
        if not isinstance(row, dict):
            continue
        title = row.get("display_name")
        if not isinstance(title, str) or not title:
            continue
        venue = None
        location = row.get("primary_location")
        if isinstance(location, dict):
            source = location.get("source")
            if isinstance(source, dict):
                name = source.get("display_name")
                venue = name if isinstance(name, str) else None
        doi = row.get("doi")
        doi = doi.removeprefix("https://doi.org/") if isinstance(doi, str) else None
        year = row.get("publication_year")
        works.append(
            RelatedWork(
                title=title,
                venue=venue,
                year=year if isinstance(year, int) else None,
                doi=doi,
                url=f"https://doi.org/{doi}" if doi else None,
                source="OpenAlex",
            )
        )
    return works


def _crossref(client: httpx.Client, query: str, mailto: str) -> list[RelatedWork]:
    response = client.get(
        CROSSREF_URL,
        params={"query.bibliographic": query, "rows": str(LIMIT), "mailto": mailto},
    )
    response.raise_for_status()
    payload = response.json()
    message = payload.get("message") if isinstance(payload, dict) else None
    items = message.get("items") if isinstance(message, dict) else None
    works: list[RelatedWork] = []
    for row in items or []:
        if not isinstance(row, dict):
            continue
        titles = row.get("title")
        title = titles[0] if isinstance(titles, list) and titles else None
        if not isinstance(title, str) or not title:
            continue
        containers = row.get("container-title")
        venue = containers[0] if isinstance(containers, list) and containers else None
        issued = row.get("issued")
        year = None
        if isinstance(issued, dict):
            parts = issued.get("date-parts")
            if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
                first = parts[0][0]
                year = first if isinstance(first, int) else None
        doi = row.get("DOI")
        doi = doi.lower() if isinstance(doi, str) else None
        works.append(
            RelatedWork(
                title=title,
                venue=venue if isinstance(venue, str) else None,
                year=year,
                doi=doi,
                url=f"https://doi.org/{doi}" if doi else None,
                source="Crossref",
            )
        )
    return works


#: A source: takes a client, a query and a contact address; returns works.
Fetcher = Callable[[httpx.Client, str, str], list[RelatedWork]]


def _dedupe(works: list[RelatedWork]) -> list[RelatedWork]:
    """One row per work. A DOI settles it; otherwise the normalised title does.

    Crossref and OpenAlex overlap heavily, and the same paper listed twice
    reads as two independent hits -- which is the opposite of what a prior-art
    panel is for.
    """
    seen: set[str] = set()
    unique: list[RelatedWork] = []
    for work in works:
        key = work.doi or work.title.casefold().strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(work)
    return unique[:LIMIT]


def search(
    db: Session,
    settings: Settings,
    *,
    title: str,
    abstract: str | None = None,
    exclude_id: Any | None = None,
) -> PriorArtResult:
    """Everything we can honestly say about whether this has been done before."""
    probe = f"{title} {abstract}".strip() if abstract else title
    similar = _similar_patents(db, title, exclude_id)

    related: list[RelatedWork] = []
    unavailable = False
    mailto = settings.import_contact_email
    query = probe[:400]

    def fetch(source: Fetcher) -> list[RelatedWork] | None:
        """None means "this source did not answer", never "it found nothing"."""
        try:
            return source(client, query, mailto)
        except (httpx.HTTPError, ValueError, KeyError, IndexError):
            return None

    try:
        # httpx.Client is thread-safe, so both lookups share one connection
        # pool and one budget instead of queueing behind each other.
        with (
            build_client(mailto, timeout=SOURCE_TIMEOUT) as client,
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            for answer in pool.map(fetch, (_openalex, _crossref)):
                if answer is None:
                    # One source being down is not a reason to lose the other,
                    # but the caller must be told the list is partial -- a
                    # short list read as a clean result is the worst thing
                    # this feature can produce.
                    unavailable = True
                else:
                    related.extend(answer)
    except httpx.HTTPError:
        unavailable = True

    return PriorArtResult(
        searched=title,
        similar_patents=similar,
        related_works=_dedupe(related),
        registries=_registries(title),
        literature_unavailable=unavailable,
    )
