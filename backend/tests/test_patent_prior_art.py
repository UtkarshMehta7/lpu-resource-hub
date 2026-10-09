"""Prior art: what we can honestly say about whether this has been done.

The feature's integrity rests on one thing -- it must never imply it has
searched the world's patents, because every open worldwide register was
tested and none can be read without a key (see `patents/priorart.py`). These
tests pin the three things it really does, and pin the honesty of the fourth.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.patents import priorart
from app.modules.users.models import UserRole
from tests.conftest import SeededUser

pytestmark = pytest.mark.db

OPENALEX_PAYLOAD = {
    "results": [
        {
            "display_name": "A tracked robot for borewell child rescue",
            "publication_year": 2019,
            "doi": "https://doi.org/10.1000/robot",
            "primary_location": {"source": {"display_name": "Journal of Field Robotics"}},
        }
    ]
}

CROSSREF_PAYLOAD = {
    "message": {
        "items": [
            {
                # The same paper OpenAlex returned, by DOI: must not appear twice.
                "title": ["A tracked robot for borewell child rescue"],
                "DOI": "10.1000/ROBOT",
                "container-title": ["Journal of Field Robotics"],
                "issued": {"date-parts": [[2019]]},
            },
            {
                "title": ["Gripper design for confined-space retrieval"],
                "DOI": "10.1000/gripper",
                "container-title": ["Mechanism and Machine Theory"],
                "issued": {"date-parts": [[2021]]},
            },
        ]
    }
}


def _transport(
    openalex: httpx.Response | Exception, crossref: httpx.Response | Exception
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        answer = openalex if "openalex" in request.url.host else crossref
        if isinstance(answer, Exception):
            raise answer
        return answer

    return httpx.MockTransport(handler)


@pytest.fixture
def patch_client(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    def _patch(openalex: httpx.Response | Exception, crossref: httpx.Response | Exception) -> None:
        def build(contact_email: str, **_: object) -> httpx.Client:
            return httpx.Client(transport=_transport(openalex, crossref))

        monkeypatch.setattr(priorart, "build_client", build)

    return _patch


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


def auth(user: SeededUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.access_token}"}


def ask(client: TestClient, user: SeededUser, title: str) -> dict[str, object]:
    response = client.post("/api/v1/patents/prior-art", json={"title": title}, headers=auth(user))
    assert response.status_code == 200, response.text
    return response.json()


def test_it_always_hands_over_the_registers_it_cannot_search(
    client: TestClient, seed_user: Callable[..., SeededUser], patch_client: Callable[..., None]
) -> None:
    # No open API covers worldwide patents, so the one thing this must always
    # do is put the query in front of the registers that can answer it.
    patch_client(httpx.Response(503), httpx.Response(503))
    result = ask(client, seed_user(UserRole.STUDENT), "A borewell rescue robot")

    names = [registry["name"] for registry in result["registries"]]
    assert names == ["Espacenet", "Google Patents", "WIPO PATENTSCOPE", "InPASS (India)"]
    assert all("borewell" in registry["url"].lower() for registry in result["registries"][:3])


def test_a_source_being_down_is_named_not_merely_counted(
    client: TestClient, seed_user: Callable[..., SeededUser], patch_client: Callable[..., None]
) -> None:
    # A short list presented as a clean result is the worst outcome here: it
    # reads as "nothing like this exists". Naming the source that failed is
    # what lets the reader judge the gap -- the two indexes do not cover the
    # same ground, so "one of them" is not an answer.
    patch_client(httpx.Response(200, json=OPENALEX_PAYLOAD), httpx.Response(500))
    result = ask(client, seed_user(UserRole.FACULTY), "A borewell rescue robot")

    assert result["unavailable_sources"] == ["Crossref"]
    # The source that did answer is still used.
    assert len(result["related_works"]) == 1


def test_the_other_source_failing_names_the_other_source(
    client: TestClient, seed_user: Callable[..., SeededUser], patch_client: Callable[..., None]
) -> None:
    # The pairing must not be hardcoded the wrong way round, which a single
    # one-sided test would never catch.
    patch_client(httpx.Response(503), httpx.Response(200, json=CROSSREF_PAYLOAD))
    result = ask(client, seed_user(UserRole.FACULTY), "A borewell rescue robot")

    assert result["unavailable_sources"] == ["OpenAlex"]
    # Both of Crossref's works survive; losing OpenAlex loses only its own.
    assert len(result["related_works"]) == 2


def test_both_sources_down_names_both(
    client: TestClient, seed_user: Callable[..., SeededUser], patch_client: Callable[..., None]
) -> None:
    patch_client(httpx.Response(503), httpx.Response(503))
    result = ask(client, seed_user(UserRole.FACULTY), "A borewell rescue robot")

    assert result["unavailable_sources"] == ["OpenAlex", "Crossref"]
    assert result["related_works"] == []


def test_the_same_paper_from_two_indexes_is_one_row(
    client: TestClient, seed_user: Callable[..., SeededUser], patch_client: Callable[..., None]
) -> None:
    # Crossref and OpenAlex overlap heavily, and one paper listed twice reads
    # as two independent hits.
    patch_client(
        httpx.Response(200, json=OPENALEX_PAYLOAD), httpx.Response(200, json=CROSSREF_PAYLOAD)
    )
    result = ask(client, seed_user(UserRole.FACULTY), "A borewell rescue robot")

    titles = [work["title"] for work in result["related_works"]]
    assert titles == [
        "A tracked robot for borewell child rescue",
        "Gripper design for confined-space retrieval",
    ]
    assert result["unavailable_sources"] == []


def test_it_finds_a_patent_already_recorded_here(
    client: TestClient, seed_user: Callable[..., SeededUser], patch_client: Callable[..., None]
) -> None:
    # Two teams in one university filing over each other is the failure this
    # can actually prevent.
    patch_client(httpx.Response(503), httpx.Response(503))
    faculty = seed_user(UserRole.FACULTY)
    existing = client.post(
        "/api/v1/patents",
        json={
            "title": "A borewell rescue robot with a self-centring gripper",
            "jurisdiction": "IN",
            "already_filed": True,
            "filing_date": "2026-02-01",
            "application_number": f"2026{uuid.uuid4().hex[:8]}",
            "inventors": [{"external_name": "A. Inventor"}],
        },
        headers=auth(faculty),
    )
    assert existing.status_code == 201

    result = ask(client, faculty, "A borewell rescue robot with a self centring gripper")
    assert [row["id"] for row in result["similar_patents"]] == [existing.json()["id"]]
    assert result["similar_patents"][0]["score"] >= 84


def test_an_unrelated_title_matches_nothing_here(
    client: TestClient, seed_user: Callable[..., SeededUser], patch_client: Callable[..., None]
) -> None:
    patch_client(httpx.Response(503), httpx.Response(503))
    faculty = seed_user(UserRole.FACULTY)
    client.post(
        "/api/v1/patents",
        json={
            "title": "A borewell rescue robot with a self-centring gripper",
            "jurisdiction": "IN",
            "already_filed": True,
            "filing_date": "2026-02-01",
            "inventors": [{"external_name": "A. Inventor"}],
        },
        headers=auth(faculty),
    )
    result = ask(client, faculty, "Courtyard geometry and indoor thermal comfort")
    assert result["similar_patents"] == []


def test_a_read_only_role_cannot_run_it(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    response = client.post(
        "/api/v1/patents/prior-art",
        json={"title": "A borewell rescue robot"},
        headers=auth(seed_user(UserRole.DEAN_OF_RESEARCH)),
    )
    assert response.status_code == 403
