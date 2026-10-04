"""The duplicate review queue: suggest, decide, and undo.

Duplicates get into the database in ways the import path cannot prevent --
two researchers each adding the same paper by hand, or a title-only record
later matched by one carrying a DOI. These tests drive the queue through the
API, because a merge deletes institutional data and the gate on it is the
point.

The band this works in is deliberate: the importer merges at title similarity
92 unattended, and this *suggests* from 84. A pair the importer would have
merged never reaches the queue, because it was merged on the way in.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.users.models import UserRole
from tests.conftest import SeededUser

pytestmark = pytest.mark.db


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


def auth(user: SeededUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.access_token}"}


@pytest.fixture
def curator(seed_user: Callable[..., SeededUser]) -> SeededUser:
    return seed_user(UserRole.ADMIN)


@pytest.fixture
def author(seed_user: Callable[..., SeededUser]) -> SeededUser:
    return seed_user(UserRole.FACULTY)


def make_publication(client: TestClient, user: SeededUser, title: str, **overrides: object) -> str:
    body: dict[str, object] = {
        "title": title,
        "abstract": None,
        "venue": "Journal of Agritech",
        "year": 2024,
        "pub_type": "journal_article",
        "authors": [{"external_name": "Jane External"}],
        **overrides,
    }
    response = client.post("/api/v1/publications", headers=auth(user), json=body)
    assert response.status_code == 201, response.text
    publication_id: str = response.json()["id"]
    return publication_id


def scan(client: TestClient, curator: SeededUser) -> dict[str, object]:
    response = client.post("/api/v1/publication-duplicates/scan", headers=auth(curator))
    assert response.status_code == 200, response.text
    data: dict[str, object] = response.json()
    return data


def queue(client: TestClient, curator: SeededUser, **params: str) -> list[dict[str, object]]:
    response = client.get("/api/v1/publication-duplicates", headers=auth(curator), params=params)
    assert response.status_code == 200, response.text
    items: list[dict[str, object]] = response.json()["items"]
    return items


# --- what the scan does and does not offer ---------------------------------


def test_a_near_identical_pair_is_suggested_with_its_evidence(
    client: TestClient, curator: SeededUser, author: SeededUser
) -> None:
    make_publication(client, author, "Forecasting wheat yield from satellite data")
    make_publication(client, author, "Forecasting wheat yield from satellite data.")

    result = scan(client, curator)

    assert result["pairs_new"] == 1
    [pair] = queue(client, curator)
    assert pair["status"] == "suspected"
    assert pair["score"] >= 84
    evidence = pair["evidence"]
    assert isinstance(evidence, dict)
    # A reviewer should be able to judge without opening both records.
    assert evidence["same_year"] is True
    assert evidence["shared_author_count"] == 1
    assert evidence["same_venue"] is True


def test_two_different_dois_are_never_offered(
    client: TestClient, curator: SeededUser, author: SeededUser
) -> None:
    """The hard rule, carried over from the importer.

    An erratum, a preprint and its version of record are separate works on
    purpose. Offering such a pair invites somebody to destroy one of them.
    """
    make_publication(client, author, "Bose-Einstein condensation", doi="10.1000/aaa")
    make_publication(client, author, "Bose-Einstein condensation", doi="10.1000/bbb")

    result = scan(client, curator)

    assert result["pairs_found"] == 0
    assert queue(client, curator) == []


def test_a_substituted_word_is_a_different_study(
    client: TestClient, curator: SeededUser, author: SeededUser
) -> None:
    """ "wheat" against "maize" scores high on a token-set ratio and is not
    the same work. Same guard the importer uses."""
    make_publication(client, author, "Forecasting wheat yield from open satellite data")
    make_publication(client, author, "Forecasting maize yield from open satellite data")

    assert scan(client, curator)["pairs_found"] == 0


def test_unrelated_publications_are_not_offered(
    client: TestClient, curator: SeededUser, author: SeededUser
) -> None:
    make_publication(client, author, "Forecasting wheat yield from satellite data")
    make_publication(client, author, "A survey of quantum error correction codes")

    assert scan(client, curator)["pairs_found"] == 0


def test_scanning_twice_adds_nothing(
    client: TestClient, curator: SeededUser, author: SeededUser
) -> None:
    make_publication(client, author, "Soil moisture sensing for smallholder farms")
    make_publication(client, author, "Soil moisture sensing for smallholder farms")

    first = scan(client, curator)
    second = scan(client, curator)

    assert first["pairs_new"] == 1
    assert second["pairs_new"] == 0
    assert len(queue(client, curator)) == 1


def test_a_decided_pair_is_not_resurrected_by_a_later_scan(
    client: TestClient, curator: SeededUser, author: SeededUser
) -> None:
    """A reviewer's judgement has to stick.

    If "these are different works" came back next week as an open item, the
    queue would never empty and people would stop reading it.
    """
    make_publication(client, author, "Nitrogen uptake in rice paddies")
    make_publication(client, author, "Nitrogen uptake in rice paddies")
    scan(client, curator)
    [pair] = queue(client, curator)
    decided = client.post(
        f"/api/v1/publication-duplicates/{pair['id']}/decision",
        headers=auth(curator),
        json={"action": "separate", "note": "Different cohorts."},
    )
    assert decided.status_code == 200, decided.text

    again = scan(client, curator)

    assert again["pairs_new"] == 0
    assert again["pairs_already_decided"] == 1
    assert queue(client, curator, status="suspected") == []
    [still] = queue(client, curator, status="separate")
    assert still["decision_note"] == "Different cohorts."
    assert still["decided_by_name"]


# --- merging ---------------------------------------------------------------


def test_merging_keeps_the_chosen_record_and_removes_the_other(
    client: TestClient, curator: SeededUser, author: SeededUser
) -> None:
    keep = make_publication(client, author, "Wheat rust resistance in Punjab")
    drop = make_publication(client, author, "Wheat rust resistance in Punjab")
    scan(client, curator)
    [pair] = queue(client, curator)

    merged = client.post(
        f"/api/v1/publication-duplicates/{pair['id']}/decision",
        headers=auth(curator),
        json={"action": "merge", "keep_id": keep},
    )

    assert merged.status_code == 200, merged.text
    assert merged.json()["status"] == "merged"
    assert merged.json()["merged_into_id"] == keep
    assert client.get(f"/api/v1/publications/{keep}", headers=auth(author)).status_code == 200
    # Gone, not hidden: a hidden row would have to be excluded from fifteen
    # queries across eight modules, and one missed is a ghost publication.
    assert client.get(f"/api/v1/publications/{drop}", headers=auth(author)).status_code == 404


def test_a_merge_has_to_name_the_survivor(
    client: TestClient, curator: SeededUser, author: SeededUser
) -> None:
    """Choosing by date would silently discard the better-described record
    half the time."""
    make_publication(client, author, "Groundwater depletion in the Doab")
    make_publication(client, author, "Groundwater depletion in the Doab")
    scan(client, curator)
    [pair] = queue(client, curator)

    response = client.post(
        f"/api/v1/publication-duplicates/{pair['id']}/decision",
        headers=auth(curator),
        json={"action": "merge"},
    )

    assert response.status_code == 422, response.text


def test_the_survivor_must_be_one_of_the_two_under_review(
    client: TestClient, curator: SeededUser, author: SeededUser
) -> None:
    make_publication(client, author, "Canal irrigation scheduling")
    make_publication(client, author, "Canal irrigation scheduling")
    stranger = make_publication(client, author, "An unrelated paper entirely")
    scan(client, curator)
    [pair] = queue(client, curator)

    response = client.post(
        f"/api/v1/publication-duplicates/{pair['id']}/decision",
        headers=auth(curator),
        json={"action": "merge", "keep_id": stranger},
    )

    assert response.status_code == 422, response.text


def test_a_merge_carries_over_authors_and_a_doi_the_survivor_lacked(
    client: TestClient, curator: SeededUser, author: SeededUser
) -> None:
    """The survivor should end up with everything either record knew.

    The DOI matters most: it is the strongest identifier either side has, and
    the column is unique, so it can only be taken once the other row is gone.
    """
    keep = make_publication(
        client, author, "Remote sensing of canal seepage", authors=[{"external_name": "A Singh"}]
    )
    make_publication(
        client,
        author,
        "Remote sensing of canal seepage",
        doi="10.1000/seepage",
        authors=[{"external_name": "A Singh"}, {"external_name": "B Kaur"}],
    )
    scan(client, curator)
    [pair] = queue(client, curator)

    client.post(
        f"/api/v1/publication-duplicates/{pair['id']}/decision",
        headers=auth(curator),
        json={"action": "merge", "keep_id": keep},
    )

    survivor = client.get(f"/api/v1/publications/{keep}", headers=auth(author)).json()
    assert survivor["doi"] == "10.1000/seepage"
    names = [a["name"] for a in survivor["authors"]]
    # B Kaur came across; A Singh was already there and is not duplicated.
    assert "B Kaur" in names
    assert names.count("A Singh") == 1


# --- undoing a merge -------------------------------------------------------


def test_a_merge_can_be_undone_and_brings_the_record_back(
    client: TestClient, curator: SeededUser, author: SeededUser
) -> None:
    """Reversible is the whole reason the losing record is snapshotted."""
    keep = make_publication(client, author, "Drip irrigation uptake in Malwa")
    make_publication(
        client,
        author,
        "Drip irrigation uptake in Malwa",
        doi="10.1000/drip",
        authors=[{"external_name": "C Gill"}],
    )
    scan(client, curator)
    [pair] = queue(client, curator)
    client.post(
        f"/api/v1/publication-duplicates/{pair['id']}/decision",
        headers=auth(curator),
        json={"action": "merge", "keep_id": keep},
    )

    undone = client.post(f"/api/v1/publication-duplicates/{pair['id']}/undo", headers=auth(curator))

    assert undone.status_code == 200, undone.text
    body = undone.json()
    assert body["status"] == "suspected"
    assert body["merged_into_id"] is None
    assert body["can_undo"] is False
    # Both sides are back, and the DOI went with the record it belongs to.
    sides = [body["publication_a"], body["publication_b"]]
    restored = [side for side in sides if side and side["doi"] == "10.1000/drip"]
    assert len(restored) == 1
    assert restored[0]["authors"] == ["C Gill"]
    survivor = client.get(f"/api/v1/publications/{keep}", headers=auth(author)).json()
    assert survivor["doi"] is None


def test_only_a_merge_can_be_undone(
    client: TestClient, curator: SeededUser, author: SeededUser
) -> None:
    make_publication(client, author, "Pesticide residue in stored grain")
    make_publication(client, author, "Pesticide residue in stored grain")
    scan(client, curator)
    [pair] = queue(client, curator)
    client.post(
        f"/api/v1/publication-duplicates/{pair['id']}/decision",
        headers=auth(curator),
        json={"action": "ignore"},
    )

    response = client.post(
        f"/api/v1/publication-duplicates/{pair['id']}/undo", headers=auth(curator)
    )

    assert response.status_code == 409, response.text


# --- who may do any of this ------------------------------------------------


def test_a_coordinator_may_curate(
    client: TestClient, seed_user: Callable[..., SeededUser], author: SeededUser
) -> None:
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)
    make_publication(client, author, "Fodder quality across seasons")
    make_publication(client, author, "Fodder quality across seasons")

    assert scan(client, coordinator)["pairs_new"] == 1


@pytest.mark.parametrize("role", [UserRole.FACULTY, UserRole.STUDENT, UserRole.DEAN_OF_RESEARCH])
def test_everybody_else_is_refused(
    client: TestClient, seed_user: Callable[..., SeededUser], role: UserRole
) -> None:
    """Merging deletes institutional records.

    A dean is included deliberately: they read the institution's figures and
    change nothing, and a merge changes the records behind the figures.
    """
    person = seed_user(role)

    scanned = client.post("/api/v1/publication-duplicates/scan", headers=auth(person))
    listed = client.get("/api/v1/publication-duplicates", headers=auth(person))

    assert scanned.status_code == 403, scanned.text
    assert listed.status_code == 403, listed.text


def test_an_unknown_review_is_a_404(client: TestClient, curator: SeededUser) -> None:
    response = client.get(
        "/api/v1/publication-duplicates/00000000-0000-0000-0000-000000000001",
        headers=auth(curator),
    )
    assert response.status_code == 404
