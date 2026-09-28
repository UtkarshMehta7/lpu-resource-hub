"""Shared shapes for the external profile connectors.

Every source answers in its own vocabulary; each connector's job is to turn
that into the two dataclasses below so the merge step never needs to know
which site a field came from. Connectors are pure readers: they fetch, they
normalise, and they never touch the database.

Why these four sources, and not the ones the brief names:

* ORCID is the identity anchor. A researcher owns their record, so the name,
  employments and work list are self-asserted rather than inferred, and the
  public API needs no key.
* OpenAlex supplies the breadth (affiliations, topics, citation metrics) that
  the brief wanted from Scopus. It is CC0 and keyless; Scopus and Web of
  Science need a paid institutional licence, which the zero-cost rule forbids.
* Crossref is the metadata authority: given a DOI, it returns the title,
  venue, type and date the publisher actually registered.
* Semantic Scholar fills in abstracts and fields of study.

DBLP was tested and rejected: it answers server-side calls with an anti-bot
challenge page rather than JSON. Google Scholar has no API and scraping it
would breach its terms, which the brief itself rules out.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from urllib.parse import unquote

import httpx

# Sent as the User-Agent and as `mailto=` where a source asks for it. Both
# Crossref and OpenAlex put identified callers in a faster "polite pool", and
# being anonymous is what gets an IP rate-limited.
USER_AGENT = "LPU-Research-Hub/1.0 (https://lpu-research-hub.netlify.app; mailto:{contact})"

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


@dataclass(frozen=True, slots=True)
class ExternalWork:
    """One publication as some external source describes it."""

    source: str
    title: str
    doi: str | None = None
    abstract: str | None = None
    venue: str | None = None
    year: int | None = None
    pub_type: str | None = None
    url: str | None = None
    authors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExternalProfile:
    """One researcher as some external source describes them."""

    source: str
    source_id: str
    source_url: str | None = None
    full_name: str | None = None
    designation: str | None = None
    affiliation: str | None = None
    bio: str | None = None
    # (label, url) pairs, matching the shape `links` already has on the profile.
    links: tuple[tuple[str, str], ...] = ()
    # Free-text subject labels. These become *suggestions* for skills and
    # research areas; they are never written into the taxonomy directly.
    topics: tuple[str, ...] = ()
    metrics: Mapping[str, int] = field(default_factory=dict)
    works: tuple[ExternalWork, ...] = ()


@dataclass(frozen=True, slots=True)
class AuthorCandidate:
    """One possible person, offered when a name search is ambiguous.

    Enough to tell yourself apart from a namesake without another round trip:
    where they work, how much they have published, and a link to the record
    itself so the choice can be checked rather than guessed at.
    """

    source: str
    source_id: str
    source_url: str | None
    full_name: str
    affiliation: str | None = None
    other_affiliations: tuple[str, ...] = ()
    orcid: str | None = None
    works_count: int | None = None
    cited_by_count: int | None = None
    h_index: int | None = None
    topics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProfileQuery:
    """What the researcher gave us to look themselves up with."""

    orcid: str | None = None
    name: str | None = None
    affiliation: str | None = None
    #: A candidate the researcher picked from a list. When set it wins over a
    #: name search: a person choosing themselves beats any fuzzy matching.
    openalex_author_id: str | None = None

    def __post_init__(self) -> None:
        if not self.orcid and not self.name and not self.openalex_author_id:
            raise ValueError("a profile query needs an ORCID iD, a name, or a chosen author")


class ConnectorError(RuntimeError):
    """A source was reachable but could not be used."""


@runtime_checkable
class ProfileConnector(Protocol):
    """One external site.

    `fetch` returns None when the source simply has no record for this
    researcher -- an ordinary outcome, not an error. It raises ConnectorError
    when the source failed in a way worth reporting.
    """

    name: str
    label: str

    def fetch(self, client: httpx.Client, query: ProfileQuery) -> ExternalProfile | None: ...


def build_client(contact_email: str, *, timeout: httpx.Timeout = DEFAULT_TIMEOUT) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT.format(contact=contact_email)},
    )


# 10.<4+ digits>/<something>. Crossref rejects anything else outright, and a
# malformed DOI in the register is worse than no DOI at all.
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")

_DOI_PREFIX = re.compile(r"^(https?://)?(dx\.)?doi\.org/|^doi:", re.IGNORECASE)


def normalise_doi(value: object) -> str | None:
    """Reduce any of the forms a DOI arrives in to the bare, lower-cased id.

    Sources are inconsistent: ORCID gives a bare DOI, Crossref gives a bare
    DOI, Semantic Scholar gives a bare DOI, and OpenAlex gives a resolver URL
    -- sometimes with the slash percent-encoded, e.g.
    `https://doi.org/10.5210%2Fdisco.v5i0.2785`. Left as-is that reaches
    Crossref as `10.5210%2fdisco...`, which it rejects with a 400 that fails
    the whole batch. Found in a live import, not in review.

    Anything that does not end up matching DOI_RE returns None rather than
    being stored as a broken identifier.
    """
    text = clean(value)
    if not text:
        return None
    text = _DOI_PREFIX.sub("", text.strip())
    if "%" in text:
        text = unquote(text)
    text = text.strip().rstrip(".").lower()
    return text[:255] if DOI_RE.match(text) else None


def clean(value: object, *, limit: int | None = None) -> str | None:
    """Collapse whitespace, drop empties, and cap length.

    External text arrives with newlines, tabs and the occasional 40KB abstract;
    every string that reaches a database column goes through here first.
    """
    if not isinstance(value, str):
        return None
    collapsed = " ".join(value.split())
    if not collapsed:
        return None
    if limit is not None and len(collapsed) > limit:
        collapsed = collapsed[: limit - 1].rstrip() + "…"
    return collapsed
