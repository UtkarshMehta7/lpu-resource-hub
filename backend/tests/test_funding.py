"""Funding calls: browsing, management and saving."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import SeededUser
from tests.world import World, auth, build_world

pytestmark = pytest.mark.db


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    return build_world(client, seed_user)


def _deadline(days: int) -> str:
    return (datetime.now(UTC).date() + timedelta(days=days)).isoformat()


def _create(
    client: TestClient, user: SeededUser, **overrides: object
) -> tuple[int, dict[str, object]]:
    body: dict[str, object] = {
        "organization": "Demo Research Council",
        "title": "Demo seed grant for low-cost sensing",
        "description": "A fictional demo call for small sensing projects.",
        "eligibility": "Demo faculty with a verified profile.",
        "amount_text": "Up to a demo amount",
        "deadline": _deadline(30),
        "official_source_url": "https://example.org/demo-call",
        **overrides,
    }
    response = client.post("/api/v1/funding", headers=auth(user), json=body)
    return response.status_code, response.json()


def test_only_coordinators_and_admins_manage_funding(client: TestClient, world: World) -> None:
    assert _create(client, world.student)[0] == 403
    assert _create(client, world.faculty)[0] == 403

    code, created = _create(client, world.coordinator)
    assert code == 201, created
    assert created["status"] == "open"
    assert created["is_demo"] is False  # only the seed script flags demo rows

    funding_id = created["id"]
    updated = client.patch(
        f"/api/v1/funding/{funding_id}",
        headers=auth(world.admin),
        json={"status": "closed", "amount_min": 50000, "amount_max": 150000},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "closed"
    assert (
        client.patch(
            f"/api/v1/funding/{funding_id}", headers=auth(world.student), json={"title": "Nope"}
        ).status_code
        == 403
    )
    assert (
        client.delete(f"/api/v1/funding/{funding_id}", headers=auth(world.faculty)).status_code
        == 403
    )
    assert (
        client.delete(f"/api/v1/funding/{funding_id}", headers=auth(world.coordinator)).status_code
        == 204
    )


def test_amount_range_and_url_are_validated(client: TestClient, world: World) -> None:
    assert _create(client, world.coordinator, amount_min=100, amount_max=10)[0] == 422
    assert _create(client, world.coordinator, official_source_url="ftp://example.org")[0] == 422
    assert (
        _create(
            client, world.coordinator, research_area_ids=["00000000-0000-0000-0000-000000000001"]
        )[0]
        == 422
    )


def test_everyone_can_browse_and_filter(client: TestClient, world: World) -> None:
    area_id = client.post(
        "/api/v1/taxonomy/research-areas",
        headers=auth(world.coordinator),
        json={"name": "Precision Farming"},
    ).json()["id"]
    _create(client, world.coordinator, research_area_ids=[area_id])
    _create(
        client,
        world.coordinator,
        title="Demo travel grant for chemistry",
        description="A fictional demo travel grant.",
        deadline=_deadline(3),
    )
    closed_id = _create(client, world.coordinator, title="Demo closed call")[1]["id"]
    client.patch(
        f"/api/v1/funding/{closed_id}", headers=auth(world.admin), json={"status": "closed"}
    )

    def titles(**params: object) -> list[str]:
        response = client.get("/api/v1/funding", headers=auth(world.student), params=params)
        assert response.status_code == 200
        return [item["title"] for item in response.json()["items"]]

    assert len(titles()) == 3
    assert titles(open_only=True) == [
        "Demo travel grant for chemistry",
        "Demo seed grant for low-cost sensing",
    ]
    assert titles(research_area_id=area_id) == ["Demo seed grant for low-cost sensing"]
    assert titles(q="travel") == ["Demo travel grant for chemistry"]
    assert titles(deadline_before=_deadline(5)) == ["Demo travel grant for chemistry"]
    assert titles(status="closed") == ["Demo closed call"]


def test_funding_can_be_saved_like_anything_else(client: TestClient, world: World) -> None:
    funding_id = _create(client, world.coordinator)[1]["id"]

    saved = client.post(
        "/api/v1/me/saved", headers=auth(world.student), json={"funding_id": funding_id}
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["saved_type"] == "funding"
    assert saved.json()["item"]["title"] == "Demo seed grant for low-cost sensing"

    # Still exactly one target per row, and still no duplicates.
    assert (
        client.post(
            "/api/v1/me/saved",
            headers=auth(world.student),
            json={"funding_id": funding_id, "project_id": world.project_id},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/me/saved", headers=auth(world.student), json={"funding_id": funding_id}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/me/saved",
            headers=auth(world.student),
            json={"funding_id": "00000000-0000-0000-0000-000000000001"},
        ).status_code
        == 404
    )

    only_funding = client.get(
        "/api/v1/me/saved", headers=auth(world.student), params={"type": "funding"}
    ).json()
    assert [entry["item"]["id"] for entry in only_funding] == [funding_id]
