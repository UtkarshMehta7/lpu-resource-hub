"""Embedding pipeline, rank fusion and hybrid search.

The vector parts are skipped when the optional ML extra isn't installed,
which is exactly the promise this step makes: the app runs either way.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.ml.embeddings import EMBEDDING_DIM, MODEL_NAME, content_hash, is_available
from app.modules.search.models import EntityEmbedding, EntityType
from app.modules.search.service import (
    build_text,
    embed_entity,
    reciprocal_rank_fusion,
    semantic_neighbours,
)
from tests.conftest import SeededUser
from tests.world import World, auth, build_world

pytestmark = pytest.mark.db

needs_ml = pytest.mark.skipif(
    not is_available(), reason="optional ML extra not installed (pip install -e '.[ml]')"
)


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    return build_world(client, seed_user)


@pytest.fixture
def session(db_settings: Settings) -> Iterator[Session]:
    engine = create_engine(str(db_settings.database_url))
    factory = sessionmaker(bind=engine)
    with factory() as db:
        yield db
    engine.dispose()


# --- pure logic (no model needed) ---------------------------------------------


def test_rank_fusion_prefers_items_both_systems_liked() -> None:
    a, b, c, d, e = (uuid.UUID(int=i) for i in range(5))
    lexical = [a, b, c, d, e]
    semantic = [e, b, c, d, a]

    fused = reciprocal_rank_fusion([lexical, semantic])

    # b is 2nd in both; a is 1st in one and last in the other. Consistently
    # good beats brilliant-once, which is the whole point of RRF.
    assert fused[0] == b
    assert fused.index(b) < fused.index(a)
    assert set(fused) == {a, b, c, d, e}


def test_rank_fusion_is_deterministic_for_ties() -> None:
    ids = [uuid.UUID(int=i) for i in range(3)]
    assert reciprocal_rank_fusion([ids]) == ids
    assert reciprocal_rank_fusion([ids, ids]) == ids
    assert reciprocal_rank_fusion([]) == []


def test_content_hash_changes_only_with_the_text() -> None:
    assert content_hash("soil sensors") == content_hash("soil sensors")
    assert content_hash("soil sensors") != content_hash("soil sensor")


def test_build_text_gathers_the_fields_that_matter(
    client: TestClient, world: World, session: Session
) -> None:
    text = build_text(session, EntityType.PROJECT, uuid.UUID(world.project_id))
    assert text is not None
    assert "soil" in text and "sensors" in text
    # A deleted or unknown entity has no document.
    assert build_text(session, EntityType.PROJECT, uuid.uuid4()) is None


# --- search endpoint behaves with or without the extra ------------------------


def test_semantic_endpoint_answers_and_reports_whether_it_was_used(
    client: TestClient, world: World
) -> None:
    response = client.get(
        "/api/v1/search/semantic",
        headers=auth(world.student),
        params={"q": "low-cost soil moisture sensors", "limit": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["semantic_used"] is is_available()
    # The lexical half alone already finds the fixture project.
    assert "Low-cost soil sensors" in [project["title"] for project in body["projects"]]


def test_semantic_search_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/search/semantic", params={"q": "anything"}).status_code == 401


# --- the vector pipeline ------------------------------------------------------


@needs_ml
def test_saving_embeds_in_the_background_and_skips_unchanged_content(
    client: TestClient, world: World, session: Session
) -> None:
    """Creating a project embeds it; re-embedding unchanged text is a no-op."""
    project_id = uuid.UUID(world.project_id)

    # The POST /projects route scheduled the embedding, which TestClient runs
    # before the response is handed back.
    stored = session.execute(
        select(EntityEmbedding).where(
            EntityEmbedding.entity_type == EntityType.PROJECT,
            EntityEmbedding.entity_id == project_id,
        )
    ).scalar_one()
    assert len(stored.embedding) == EMBEDDING_DIM
    assert stored.model_name == MODEL_NAME
    assert stored.content_hash == content_hash(
        build_text(session, EntityType.PROJECT, project_id) or ""
    )
    first_hash = stored.content_hash

    # Nothing changed, so no work and no new row.
    assert embed_entity(session, EntityType.PROJECT, project_id) is False

    client.patch(
        f"/api/v1/projects/{world.project_id}",
        headers=auth(world.faculty),
        json={"summary": "Now about hydroponics and nutrient films instead."},
    )
    session.expire_all()
    refreshed = session.execute(
        select(EntityEmbedding).where(
            EntityEmbedding.entity_type == EntityType.PROJECT,
            EntityEmbedding.entity_id == project_id,
        )
    ).scalar_one()
    assert refreshed.content_hash != first_hash


@needs_ml
def test_semantic_search_finds_wording_the_lexical_search_misses(
    client: TestClient, world: World, session: Session
) -> None:
    """The fixture project says 'soil moisture sensors', never 'agriculture'."""
    embed_entity(session, EntityType.PROJECT, uuid.UUID(world.project_id))

    query = "equipment for measuring how wet farmland is"
    lexical = client.get("/api/v1/search", headers=auth(world.student), params={"q": query})
    assert lexical.status_code == 200
    assert lexical.json()["projects"] == []

    neighbours = semantic_neighbours(session, query, EntityType.PROJECT, limit=5)
    assert uuid.UUID(world.project_id) in [entity_id for entity_id, _ in neighbours]


@needs_ml
def test_hidden_projects_never_reach_semantic_results(
    client: TestClient, world: World, session: Session
) -> None:
    """A draft is embedded like anything else, but must not be searchable."""
    embed_entity(session, EntityType.PROJECT, uuid.UUID(world.draft_project_id))

    response = client.get(
        "/api/v1/search/semantic",
        headers=auth(world.student),
        params={"q": "unpublished work", "limit": 10},
    )
    ids = [project["id"] for project in response.json()["projects"]]
    assert world.draft_project_id not in ids
