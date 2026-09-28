"""The profile-import endpoints.

The external sites are stubbed throughout: a test suite that reaches ORCID
over the network is slow, flaky and rude, and what is worth testing here is
the policy around the import -- who may run one, what it refuses to overwrite,
and that a publication already in the register is never duplicated -- not
whether httpx can make a GET.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.imports import service
from app.modules.imports.connectors.base import ExternalProfile, ExternalWork
from app.modules.imports.merge import merge_profiles
from tests.conftest import SeededUser
from tests.world import World, auth, build_world

pytestmark = pytest.mark.db

ORCID = "0000-0002-1825-0097"


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    return build_world(client, seed_user)


def fake_sources(
    *works: ExternalWork,
    designation: str | None = "Associate Professor",
    bio: str | None = "Works on soil moisture sensing.",
    links: tuple[tuple[str, str], ...] = (("Lab page", "https://example.edu/lab"),),
) -> Callable[..., tuple[object, dict[str, str]]]:
    """Replaces the network fan-out with a fixed answer."""
    profile = ExternalProfile(
        source="orcid",
        source_id=ORCID,
        source_url=f"https://orcid.org/{ORCID}",
        full_name="Seeded faculty",
        designation=designation,
        affiliation="Lovely Professional University",
        bio=bio,
        links=links,
        topics=("Soil Science", "Remote Sensing"),
        works=works,
    )

    def _gather(query: object) -> tuple[object, dict[str, str]]:
        return merge_profiles([profile], works), {}

    return _gather


def paper(title: str, **kwargs: object) -> ExternalWork:
    doi = kwargs.get("doi")
    year = kwargs.get("year", 2023)
    return ExternalWork(
        source="orcid",
        title=title,
        doi=doi if isinstance(doi, str) else None,
        venue="Journal of Soil Science",
        year=year if isinstance(year, int) else None,
        pub_type="journal-article",
        authors=("Seeded faculty", "A Collaborator"),
    )


# ------------------------------------------------------------------ access


def test_preview_needs_something_to_look_up(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/me/profile/import/preview", headers=auth(world.faculty), json={}
    )
    assert response.status_code == 422


def test_a_malformed_orcid_is_refused_before_any_network_call(
    client: TestClient, world: World
) -> None:
    response = client.post(
        "/api/v1/me/profile/import/preview",
        headers=auth(world.faculty),
        json={"orcid": "definitely-not-an-orcid"},
    )
    assert response.status_code == 422


def test_signing_in_is_required(client: TestClient) -> None:
    response = client.post("/api/v1/me/profile/import/preview", json={"orcid": ORCID})
    assert response.status_code == 401


def test_a_student_has_no_researcher_profile_to_import_into(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "_gather", fake_sources(paper("Anything", doi="10.1/x")))
    response = client.post(
        "/api/v1/me/profile/import/preview",
        headers=auth(world.student),
        json={"orcid": ORCID},
    )
    assert response.status_code == 409


# ----------------------------------------------------------------- preview


def test_preview_reports_what_would_change_without_changing_it(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        service, "_gather", fake_sources(paper("Soil moisture at scale", doi="10.1/new"))
    )
    response = client.post(
        "/api/v1/me/profile/import/preview",
        headers=auth(world.faculty),
        json={"orcid": ORCID},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["new_count"] == 1
    assert body["works"][0]["status"] == "new"
    assert body["works"][0]["importable"] is True
    bio_field = next(f for f in body["fields"] if f["field"] == "bio")
    assert bio_field["changed"] is True

    # Nothing was written: the profile still has its original bio.
    profile = client.get("/api/v1/me/profile", headers=auth(world.faculty)).json()
    assert profile["bio"] == "Soil moisture sensing for farms."


def test_a_work_without_a_year_is_reported_but_not_importable(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        service, "_gather", fake_sources(paper("Undated manuscript", doi="10.1/u", year=None))
    )
    body = client.post(
        "/api/v1/me/profile/import/preview",
        headers=auth(world.faculty),
        json={"orcid": ORCID},
    ).json()
    assert body["works"][0]["status"] == "not_importable"
    assert body["works"][0]["importable"] is False


# ------------------------------------------------------------------- apply


def test_apply_writes_only_the_ticked_fields_and_works(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        service,
        "_gather",
        fake_sources(
            paper("Chosen paper", doi="10.1/chosen"),
            paper("Ignored paper", doi="10.1/ignored"),
        ),
    )
    preview = client.post(
        "/api/v1/me/profile/import/preview",
        headers=auth(world.faculty),
        json={"orcid": ORCID},
    ).json()
    chosen = next(w["key"] for w in preview["works"] if w["title"] == "Chosen paper")

    response = client.post(
        "/api/v1/me/profile/import",
        headers=auth(world.faculty),
        json={"orcid": ORCID, "fields": ["bio"], "work_keys": [chosen]},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["works_imported"] == 1
    assert result["applied_fields"] == ["bio"]

    profile = client.get("/api/v1/me/profile", headers=auth(world.faculty)).json()
    assert profile["bio"] == "Works on soil moisture sensing."
    # designation was not ticked, so it was left alone.
    assert profile["designation"] == "Professor"

    titles = {
        item["title"]
        for item in client.get(
            "/api/v1/publications", headers=auth(world.faculty), params={"q": "paper"}
        ).json()["items"]
    }
    assert "Chosen paper" in titles
    assert "Ignored paper" not in titles


def test_importing_the_same_work_twice_does_not_duplicate_it(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "_gather", fake_sources(paper("Only once", doi="10.1/once")))
    first = client.post(
        "/api/v1/me/profile/import/preview",
        headers=auth(world.faculty),
        json={"orcid": ORCID},
    ).json()
    key = first["works"][0]["key"]
    client.post(
        "/api/v1/me/profile/import",
        headers=auth(world.faculty),
        json={"orcid": ORCID, "fields": [], "work_keys": [key]},
    )

    # Second run: the preview now recognises it, and applying imports nothing.
    second = client.post(
        "/api/v1/me/profile/import/preview",
        headers=auth(world.faculty),
        json={"orcid": ORCID},
    ).json()
    assert second["works"][0]["status"] == "already_in_register"
    assert second["known_count"] == 1

    again = client.post(
        "/api/v1/me/profile/import",
        headers=auth(world.faculty),
        json={"orcid": ORCID, "fields": [], "work_keys": [key]},
    ).json()
    assert again["works_imported"] == 0
    assert again["works_skipped"] == 1


def test_two_accounts_cannot_claim_the_same_orcid(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "_gather", fake_sources(paper("Shared", doi="10.1/s")))
    client.post(
        "/api/v1/me/profile/import",
        headers=auth(world.faculty),
        json={"orcid": ORCID, "fields": [], "work_keys": []},
    )
    response = client.post(
        "/api/v1/me/profile/import/preview",
        headers=auth(world.other_faculty),
        json={"orcid": ORCID},
    )
    assert response.status_code == 409


def test_an_import_is_recorded_in_the_callers_history(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "_gather", fake_sources(paper("Recorded", doi="10.1/r")))
    preview = client.post(
        "/api/v1/me/profile/import/preview",
        headers=auth(world.faculty),
        json={"orcid": ORCID},
    ).json()
    client.post(
        "/api/v1/me/profile/import",
        headers=auth(world.faculty),
        json={"orcid": ORCID, "fields": ["bio"], "work_keys": [preview["works"][0]["key"]]},
    )
    history = client.get("/api/v1/me/profile/import/history", headers=auth(world.faculty)).json()
    assert len(history) == 1
    assert history[0]["works_imported"] == 1
    assert history[0]["orcid_id"] == ORCID

    # And it is the caller's own history, not anyone else's.
    other = client.get(
        "/api/v1/me/profile/import/history", headers=auth(world.other_faculty)
    ).json()
    assert other == []


def test_nobody_can_import_into_another_researchers_profile(client: TestClient) -> None:
    """There is deliberately no route for it -- assert it stays that way."""
    paths = client.get("/openapi.json").json()["paths"]
    importing = [p for p in paths if "import" in p]
    # Every one is scoped to /me. Adding a route here should be a decision,
    # which is what this assertion forces.
    assert sorted(importing) == [
        "/api/v1/me/profile/import",
        "/api/v1/me/profile/import/candidates",
        "/api/v1/me/profile/import/history",
        "/api/v1/me/profile/import/preview",
    ]


# --- choosing between namesakes --------------------------------------------


def test_an_import_sends_a_verified_profile_back_for_review(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reason this exists: an import puts claims nobody here has checked
    onto a profile somebody already signed off."""
    before = client.get("/api/v1/me/profile", headers=auth(world.faculty)).json()
    assert before["verification_status"] == "verified"

    monkeypatch.setattr(service, "_gather", fake_sources(paper("A paper", doi="10.1234/x")))
    preview = client.post(
        "/api/v1/me/profile/import/preview",
        headers=auth(world.faculty),
        json={"orcid": ORCID},
    ).json()
    result = client.post(
        "/api/v1/me/profile/import",
        headers=auth(world.faculty),
        json={"orcid": ORCID, "fields": ["bio"], "work_keys": [preview["works"][0]["key"]]},
    ).json()

    assert result["verification_reset"] is True
    after = client.get("/api/v1/me/profile", headers=auth(world.faculty)).json()
    assert after["verification_status"] == "pending"
    assert after["verified_at"] is None


def test_an_import_that_changes_nothing_leaves_verification_alone(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "_gather", fake_sources(paper("Untouched", doi="10.1234/y")))
    result = client.post(
        "/api/v1/me/profile/import",
        headers=auth(world.faculty),
        json={"orcid": ORCID, "fields": [], "work_keys": []},
    ).json()

    assert result["verification_reset"] is False
    after = client.get("/api/v1/me/profile", headers=auth(world.faculty)).json()
    assert after["verification_status"] == "verified"


def test_every_work_carries_a_link_so_it_can_be_checked(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        service, "_gather", fake_sources(paper("Checkable", doi="10.1234/checkable"))
    )
    body = client.post(
        "/api/v1/me/profile/import/preview",
        headers=auth(world.faculty),
        json={"orcid": ORCID},
    ).json()
    work = body["works"][0]
    # A DOI is enough to build a link; `url` is the fallback for works
    # without one, and the field must exist either way.
    assert "url" in work
    assert work["doi"] == "10.1234/checkable"


def test_candidate_search_needs_a_real_name(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/me/profile/import/candidates", headers=auth(world.faculty), json={"name": "a"}
    )
    assert response.status_code == 422


def test_a_student_cannot_search_for_candidates(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/me/profile/import/candidates",
        headers=auth(world.student),
        json={"name": "Someone Plausible"},
    )
    assert response.status_code == 409
