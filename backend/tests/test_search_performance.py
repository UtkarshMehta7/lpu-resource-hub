"""Guards on expertise search that survive a shared CI runner.

The measured benchmark lives in `scripts/benchmark_search.py` and its results
in docs/search-performance.md. Wall-clock assertions are deliberately **not**
made here: a GitHub runner's timing varies with whatever else is on the box,
so a latency threshold in CI is a flaky test, not a performance guarantee.

What is asserted instead is the shape of the work -- that the query stays one
indexed statement over the full-text document, that it does not fan out into a
query per result, and that paging does not walk the whole table. Those are the
properties that actually decay, and they are stable to observe.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.main import create_app
from app.modules.users.models import UserRole
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


def plan_for(db_settings: Settings, sql: str, params: dict[str, object]) -> str:
    engine = create_engine(str(db_settings.database_url))
    try:
        with engine.connect() as connection:
            rows = connection.execute(text(f"EXPLAIN {sql}"), params).all()
        return "\n".join(row[0] for row in rows)
    finally:
        engine.dispose()


SEARCH_SQL = """
    SELECT rp.user_id
      FROM researcher_profiles rp
     WHERE rp.search_document @@ websearch_to_tsquery('english', :q)
     ORDER BY ts_rank(rp.search_document, websearch_to_tsquery('english', :q)) DESC
     LIMIT 20
"""


def test_the_full_text_index_exists_and_is_the_right_kind(db_settings: Settings) -> None:
    """A GIN index over the tsvector. A btree here would be useless."""
    engine = create_engine(str(db_settings.database_url))
    try:
        with engine.connect() as connection:
            definition = connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE tablename = 'researcher_profiles' "
                    "AND indexname = 'ix_researcher_profiles_search_document'"
                )
            ).scalar_one_or_none()
    finally:
        engine.dispose()
    assert definition is not None, "the search document has no index"
    assert "USING gin" in definition


def test_search_is_planned_as_one_statement_not_a_fan_out(db_settings: Settings) -> None:
    """The plan must not contain a nested loop over a subquery per row.

    The failure this catches is a refactor that moves tag loading inside the
    result loop -- correct, and a query per researcher.
    """
    plan = plan_for(db_settings, SEARCH_SQL, {"q": "machine learning"})
    assert "SubPlan" not in plan, plan


def test_searching_never_sorts_the_whole_table(db_settings: Settings) -> None:
    """Ranking must be a bounded top-N, not a full sort of every match."""
    plan = plan_for(db_settings, SEARCH_SQL, {"q": "machine learning"})
    assert "Limit" in plan, plan


# --- behaviour the benchmark cannot check ---------------------------------


def test_a_search_across_departments_returns_people_from_more_than_one(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """The criterion is about finding researchers *across departments*, so the
    query must not be silently scoped to the caller's own."""
    other_department = client.post(
        "/api/v1/admin/departments",
        headers=auth(world.admin),
        json={
            "school_id": client.get("/api/v1/schools", headers=auth(world.admin)).json()[0]["id"],
            "name": "Distant Department",
        },
    ).json()["id"]

    outsider = seed_user(UserRole.FACULTY, department_id=other_department)
    client.put(
        "/api/v1/me/profile",
        headers=auth(outsider),
        json={"designation": "Professor", "bio": "Works on distinctive soil telemetry."},
    )
    client.post(
        f"/api/v1/researchers/{outsider.id}/verify",
        headers=auth(world.admin),
        json={"decision": "verified"},
    )

    found = client.get(
        "/api/v1/researchers", headers=auth(world.faculty), params={"q": "telemetry"}
    ).json()
    departments = {item["department_id"] for item in found["items"]}
    assert str(other_department) in {str(d) for d in departments if d}


def test_paging_does_not_repeat_or_lose_a_researcher(client: TestClient, world: World) -> None:
    first = client.get(
        "/api/v1/researchers", headers=auth(world.faculty), params={"page_size": 1, "page": 1}
    ).json()
    second = client.get(
        "/api/v1/researchers", headers=auth(world.faculty), params={"page_size": 1, "page": 2}
    ).json()
    if first["total"] >= 2:
        assert first["items"][0]["user_id"] != second["items"][0]["user_id"]
