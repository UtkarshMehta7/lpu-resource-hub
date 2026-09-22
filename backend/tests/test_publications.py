"""Publication ownership, author constraints, DOI uniqueness, filters (real PostgreSQL)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

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


def _auth(user: SeededUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.access_token}"}


@dataclass
class World:
    admin: SeededUser
    author: SeededUser
    coauthor: SeededUser
    other_faculty: SeededUser
    student: SeededUser


@pytest.fixture
def world(seed_user: Callable[..., SeededUser]) -> World:
    return World(
        admin=seed_user(UserRole.ADMIN),
        author=seed_user(UserRole.FACULTY),
        coauthor=seed_user(UserRole.FACULTY),
        other_faculty=seed_user(UserRole.FACULTY),
        student=seed_user(UserRole.STUDENT),
    )


def _body(**overrides: object) -> dict[str, object]:
    return {
        "title": "Graph neural networks for crop yield",
        "abstract": "We predict crop yield with graph neural networks.",
        "venue": "Journal of Agritech",
        "year": 2024,
        "pub_type": "journal_article",
        "authors": [{"external_name": "Jane External"}],
        **overrides,
    }


def _create(client: TestClient, user: SeededUser, **overrides: object) -> dict[str, object]:
    response = client.post("/api/v1/publications", headers=_auth(user), json=_body(**overrides))
    assert response.status_code == 201, response.text
    data: dict[str, object] = response.json()
    return data


def test_create_keeps_author_order_and_resolves_internal_names(
    client: TestClient, world: World
) -> None:
    created = _create(
        client,
        world.author,
        authors=[
            {"user_id": str(world.author.id)},
            {"external_name": "Jane External"},
            {"user_id": str(world.coauthor.id)},
        ],
    )
    authors = created["authors"]
    assert isinstance(authors, list)
    assert [a["author_order"] for a in authors] == [1, 2, 3]
    assert authors[0]["user_id"] == str(world.author.id)
    assert authors[1] == {"user_id": None, "name": "Jane External", "author_order": 2}
    assert created["created_by"] == str(world.author.id)


def test_student_cannot_create(client: TestClient, world: World) -> None:
    response = client.post("/api/v1/publications", headers=_auth(world.student), json=_body())
    assert response.status_code == 403


@pytest.mark.parametrize(
    "author",
    [{}, {"user_id": "00000000-0000-0000-0000-000000000001", "external_name": "Both"}],
)
def test_author_needs_exactly_one_identity(
    client: TestClient, world: World, author: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/publications", headers=_auth(world.author), json=_body(authors=[author])
    )
    assert response.status_code == 422


def test_empty_author_list_rejected(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/publications", headers=_auth(world.author), json=_body(authors=[])
    )
    assert response.status_code == 422


def test_unknown_internal_author_rejected(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/publications",
        headers=_auth(world.author),
        json=_body(authors=[{"user_id": "00000000-0000-0000-0000-000000000001"}]),
    )
    assert response.status_code == 422


def test_year_out_of_range_rejected(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/publications", headers=_auth(world.author), json=_body(year=1500)
    )
    assert response.status_code == 422


def test_db_enforces_exactly_one_author_identity(
    client: TestClient, world: World, db_settings: Settings
) -> None:
    publication_id = _create(client, world.author)["id"]
    engine = create_engine(str(db_settings.database_url))
    try:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO publication_authors (publication_id, author_order) "
                    "VALUES (:pid, 5)"
                ),
                {"pid": publication_id},
            )
    finally:
        engine.dispose()


def test_doi_is_unique_after_normalisation(client: TestClient, world: World) -> None:
    created = _create(client, world.author, doi="10.1000/ABC.123")
    assert created["doi"] == "10.1000/abc.123"
    response = client.post(
        "/api/v1/publications",
        headers=_auth(world.other_faculty),
        json=_body(title="Other", doi="https://doi.org/10.1000/abc.123"),
    )
    assert response.status_code == 409


def test_doi_conflict_on_update(client: TestClient, world: World) -> None:
    _create(client, world.author, doi="10.1/one")
    second = _create(client, world.author, title="Second", doi="10.1/two")
    response = client.patch(
        f"/api/v1/publications/{second['id']}",
        headers=_auth(world.author),
        json={"doi": "10.1/ONE"},
    )
    assert response.status_code == 409


def test_only_creator_can_edit(client: TestClient, world: World) -> None:
    publication_id = _create(client, world.author, authors=[{"user_id": str(world.coauthor.id)}])[
        "id"
    ]
    for intruder in (world.coauthor, world.other_faculty, world.admin):
        response = client.patch(
            f"/api/v1/publications/{publication_id}",
            headers=_auth(intruder),
            json={"title": "Hijacked"},
        )
        assert response.status_code == 403
    response = client.patch(
        f"/api/v1/publications/{publication_id}",
        headers=_auth(world.author),
        json={"title": "Renamed", "authors": [{"external_name": "Solo"}], "venue": None},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Renamed"
    assert body["venue"] is None
    assert [a["name"] for a in body["authors"]] == ["Solo"]


def test_delete_by_creator_or_admin_only(client: TestClient, world: World) -> None:
    first = _create(client, world.author)["id"]
    second = _create(client, world.author, title="Second")["id"]
    assert (
        client.delete(f"/api/v1/publications/{first}", headers=_auth(world.other_faculty))
    ).status_code == 403
    assert (
        client.delete(f"/api/v1/publications/{first}", headers=_auth(world.author))
    ).status_code == 204
    assert (
        client.get(f"/api/v1/publications/{first}", headers=_auth(world.author))
    ).status_code == 404
    assert (
        client.delete(f"/api/v1/publications/{second}", headers=_auth(world.admin))
    ).status_code == 204
    logs = client.get("/api/v1/admin/audit-logs", headers=_auth(world.admin)).json()["items"]
    assert any(log["action"] == "publication.deleted" for log in logs)


def test_everyone_can_read(client: TestClient, world: World) -> None:
    publication_id = _create(client, world.author)["id"]
    response = client.get(f"/api/v1/publications/{publication_id}", headers=_auth(world.student))
    assert response.status_code == 200


def test_author_filter_includes_coauthored_and_created(client: TestClient, world: World) -> None:
    _create(client, world.author, title="Own", authors=[{"external_name": "X"}])
    _create(
        client,
        world.other_faculty,
        title="Coauthored",
        authors=[{"user_id": str(world.author.id)}],
    )
    _create(client, world.other_faculty, title="Unrelated")
    response = client.get(
        "/api/v1/publications",
        headers=_auth(world.student),
        params={"author_id": str(world.author.id)},
    )
    assert sorted(p["title"] for p in response.json()["items"]) == ["Coauthored", "Own"]


def test_year_and_text_filters(client: TestClient, world: World) -> None:
    _create(client, world.author, title="Neural crops", year=2023)
    _create(client, world.author, title="Protein folding", abstract="Chemistry.", year=2024)
    by_year = client.get(
        "/api/v1/publications", headers=_auth(world.student), params={"year": 2023}
    ).json()
    assert [p["title"] for p in by_year["items"]] == ["Neural crops"]
    by_q = client.get(
        "/api/v1/publications", headers=_auth(world.student), params={"q": "protein"}
    ).json()
    assert [p["title"] for p in by_q["items"]] == ["Protein folding"]
    search = client.get(
        "/api/v1/search", headers=_auth(world.student), params={"q": "protein"}
    ).json()
    assert [p["title"] for p in search["publications"]] == ["Protein folding"]


def test_project_links_owned_only_and_hidden_when_invisible(
    client: TestClient, world: World
) -> None:
    project_id = client.post(
        "/api/v1/projects",
        headers=_auth(world.author),
        json={"title": "Draft project", "summary": "S", "description": "D"},
    ).json()["id"]
    # Someone else can't link to the author's project.
    response = client.post(
        "/api/v1/publications",
        headers=_auth(world.other_faculty),
        json=_body(project_ids=[project_id]),
    )
    assert response.status_code == 422

    created = _create(client, world.author, project_ids=[project_id])
    assert created["projects"] == [{"id": project_id, "title": "Draft project"}]
    # The project is a draft: others see the publication, not the link.
    as_student = client.get(
        f"/api/v1/publications/{created['id']}", headers=_auth(world.student)
    ).json()
    assert as_student["projects"] == []
    filtered = client.get(
        "/api/v1/publications",
        headers=_auth(world.student),
        params={"project_id": project_id},
    ).json()
    assert filtered["total"] == 0
    own = client.get(
        "/api/v1/publications", headers=_auth(world.author), params={"project_id": project_id}
    ).json()
    assert own["total"] == 1
