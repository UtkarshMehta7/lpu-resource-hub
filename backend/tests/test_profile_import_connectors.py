"""Connector behaviour under bad data, with the network stubbed.

These cover the failure modes the brief calls for -- "import resilience to
malformed external records" -- rather than the happy path, because the happy
path is what a live run exercises and the failures are what a live run only
finds occasionally.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from app.modules.imports.connectors.base import ProfileQuery
from app.modules.imports.connectors.crossref import CrossrefConnector
from app.modules.imports.connectors.openalex import OpenAlexConnector
from app.modules.imports.connectors.orcid import OrcidConnector
from app.modules.imports.connectors.semantic_scholar import SemanticScholarConnector

GOOD = "10.1234/good"
ALSO_GOOD = "10.1234/also-good"
# Valid in shape, but Crossref refuses it -- the case that used to fail a
# whole 40-DOI batch and lose the metadata for every paper in it.
REFUSED = "10.5210/refused.v5i0.1"


def crossref_stub(request: httpx.Request) -> httpx.Response:
    """Answers 400 for any batch containing the refused DOI, like the real one."""
    filters = request.url.params.get("filter", "")
    dois = [part.removeprefix("doi:") for part in filters.split(",")]
    if REFUSED in dois:
        return httpx.Response(400, json={"status": "failed"})
    items = [
        {
            "DOI": doi,
            "title": [f"Paper {doi}"],
            "container-title": ["A Journal"],
            "issued": {"date-parts": [[2021]]},
            "type": "journal-article",
        }
        for doi in dois
    ]
    return httpx.Response(200, json={"message": {"items": items}})


Handler = Callable[[httpx.Request], httpx.Response]


def client_for(handler: Handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_one_refused_doi_does_not_lose_the_rest_of_the_batch() -> None:
    with client_for(crossref_stub) as client:
        found = CrossrefConnector("t@e.com").enrich(client, [GOOD, REFUSED, ALSO_GOOD])
    # The offender is dropped; both good records survive.
    assert set(found) == {GOOD, ALSO_GOOD}


def test_malformed_dois_never_reach_the_network() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params.get("filter", ""))
        return httpx.Response(200, json={"message": {"items": []}})

    with client_for(handler) as client:
        CrossrefConnector("t@e.com").enrich(client, ["not-a-doi", "10.1/short", "", GOOD])
    assert seen == [f"doi:{GOOD}"]


def test_a_source_that_is_down_raises_rather_than_returning_half_a_profile() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    from app.modules.imports.connectors.base import ConnectorError

    with client_for(handler) as client, pytest.raises(ConnectorError):
        OpenAlexConnector("t@e.com").fetch(client, ProfileQuery(orcid="0000-0003-1613-5981"))


def test_semantic_scholar_being_throttled_is_not_an_error() -> None:
    """Keyless callers share a rate-limited pool, so 429 is routine."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "Too Many Requests"})

    with client_for(handler) as client:
        assert SemanticScholarConnector().enrich(client, [GOOD]) == {}


def test_an_orcid_record_stripped_of_every_optional_field_still_parses() -> None:
    """Real records omit almost anything; none of it may raise."""
    record = {
        "person": {"name": None, "biography": None, "researcher-urls": None, "keywords": None},
        "activities-summary": {"employments": None, "works": None},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=record)

    with client_for(handler) as client:
        profile = OrcidConnector().fetch(client, ProfileQuery(orcid="0000-0002-1825-0097"))
    assert profile is not None
    assert profile.full_name is None
    assert profile.works == ()
    assert profile.links == ()


def test_an_unknown_orcid_is_reported_as_no_record_not_an_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with client_for(handler) as client:
        assert OrcidConnector().fetch(client, ProfileQuery(orcid="0000-0002-1825-0097")) is None


def test_openalex_refuses_to_guess_when_one_orcid_has_several_author_records() -> None:
    """ORCID's own demo iD resolves to dozens of real OpenAlex authors."""
    from app.modules.imports.connectors.base import ConnectorError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": f"https://openalex.org/A{n}",
                        "display_name": f"Someone Else {n}",
                        "orcid": "https://orcid.org/0000-0002-1825-0097",
                    }
                    for n in range(3)
                ]
            },
        )

    with client_for(handler) as client, pytest.raises(ConnectorError):
        OpenAlexConnector("t@e.com").fetch(client, ProfileQuery(orcid="0000-0002-1825-0097"))


def test_openalex_rebuilds_an_abstract_from_its_inverted_index() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/authors" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "https://openalex.org/A1",
                            "display_name": "A Researcher",
                            "orcid": "https://orcid.org/0000-0003-1613-5981",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "display_name": "A paper",
                        "publication_year": 2020,
                        "abstract_inverted_index": {"Graphs": [0], "are": [1], "useful": [2]},
                    }
                ]
            },
        )

    with client_for(handler) as client:
        profile = OpenAlexConnector("t@e.com").fetch(
            client, ProfileQuery(orcid="0000-0003-1613-5981")
        )
    assert profile is not None
    assert profile.works[0].abstract == "Graphs are useful"


def test_a_source_returning_nonsense_json_does_not_crash_the_import() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=json.dumps([1, 2, 3]), headers={"content-type": "application/json"}
        )

    with client_for(handler) as client:
        assert SemanticScholarConnector().enrich(client, [GOOD]) == {}
