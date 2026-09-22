"""Researcher directory, student discovery and search integration tests."""

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


def _auth(user: SeededUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.access_token}"}


def _department(client: TestClient, admin: SeededUser, name: str) -> str:
    school_id = client.post(
        "/api/v1/admin/schools", headers=_auth(admin), json={"name": f"{name} School"}
    ).json()["id"]
    department_id: str = client.post(
        "/api/v1/admin/departments",
        headers=_auth(admin),
        json={"school_id": school_id, "name": name},
    ).json()["id"]
    return department_id


def _skill(client: TestClient, admin: SeededUser, name: str) -> str:
    skill_id: str = client.post(
        "/api/v1/taxonomy/skills", headers=_auth(admin), json={"name": name}
    ).json()["id"]
    return skill_id


def _area(client: TestClient, admin: SeededUser, name: str, parent_id: str | None = None) -> str:
    body: dict[str, object] = {"name": name}
    if parent_id:
        body["parent_id"] = parent_id
    area_id: str = client.post(
        "/api/v1/taxonomy/research-areas", headers=_auth(admin), json=body
    ).json()["id"]
    return area_id


def _make_researcher(
    client: TestClient,
    admin: SeededUser,
    researcher: SeededUser,
    *,
    designation: str = "Assistant Professor",
    bio: str | None = None,
    availability: str = "available",
    skill_ids: list[str] | None = None,
    area_ids: list[str] | None = None,
    verify: bool = True,
) -> None:
    client.put(
        "/api/v1/me/profile",
        headers=_auth(researcher),
        json={"designation": designation, "bio": bio, "availability": availability},
    )
    if skill_ids:
        client.put(
            "/api/v1/me/skills",
            headers=_auth(researcher),
            json=[{"skill_id": sid, "proficiency": 4} for sid in skill_ids],
        )
    if area_ids:
        client.put(
            "/api/v1/me/research-areas",
            headers=_auth(researcher),
            json=[{"research_area_id": aid, "is_expertise": True} for aid in area_ids],
        )
    if verify:
        client.post(
            f"/api/v1/researchers/{researcher.id}/verify",
            headers=_auth(admin),
            json={"decision": "verified"},
        )


def test_directory_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/researchers").status_code == 401


def test_directory_lists_researchers_without_email(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    faculty = seed_user(UserRole.FACULTY)
    student = seed_user(UserRole.STUDENT)
    _make_researcher(client, admin, faculty, designation="Professor of Robotics")

    response = client.get("/api/v1/researchers", headers=_auth(student))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    card = body["items"][0]
    assert card["designation"] == "Professor of Robotics"
    # Public schema: no email, ever.
    assert "email" not in card


def test_full_text_search_matches_skills_and_areas(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    match = seed_user(UserRole.FACULTY)
    other = seed_user(UserRole.FACULTY)
    skill = _skill(client, admin, "Kubernetes")
    _make_researcher(client, admin, match, skill_ids=[skill])
    _make_researcher(client, admin, other, designation="Lecturer in Poetry")

    response = client.get("/api/v1/researchers", params={"q": "kubernetes"}, headers=_auth(admin))

    assert response.status_code == 200
    ids = [item["user_id"] for item in response.json()["items"]]
    assert ids == [str(match.id)]


def test_search_tolerates_a_misspelled_name(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    """The trigram index is what makes this work; plain FTS would miss it."""
    admin = seed_user(UserRole.ADMIN)
    faculty = seed_user(UserRole.FACULTY, email="kowalski@example.com")
    _make_researcher(client, admin, faculty)

    exact = client.get("/api/v1/researchers", params={"q": "Seeded faculty"}, headers=_auth(admin))
    typo = client.get("/api/v1/researchers", params={"q": "Seedd facluty"}, headers=_auth(admin))

    assert [i["user_id"] for i in exact.json()["items"]] == [str(faculty.id)]
    assert [i["user_id"] for i in typo.json()["items"]] == [str(faculty.id)]


def test_filter_by_research_area_includes_child_areas(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    faculty = seed_user(UserRole.FACULTY)
    parent = _area(client, admin, "Artificial Intelligence")
    child = _area(client, admin, "Machine Learning", parent_id=parent)
    _make_researcher(client, admin, faculty, area_ids=[child])

    response = client.get(
        "/api/v1/researchers", params={"research_area_id": parent}, headers=_auth(admin)
    )

    assert [i["user_id"] for i in response.json()["items"]] == [str(faculty.id)]


def test_filter_by_department_skill_availability_and_verified(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    department = _department(client, admin, "Physics")
    skill = _skill(client, admin, "Optics")
    wanted = seed_user(UserRole.FACULTY, department_id=department)
    unverified = seed_user(UserRole.FACULTY, department_id=department)
    _make_researcher(client, admin, wanted, availability="limited", skill_ids=[skill])
    _make_researcher(client, admin, unverified, verify=False)

    def ids(params: dict[str, object]) -> list[str]:
        return [
            item["user_id"]
            for item in client.get(
                "/api/v1/researchers", params=params, headers=_auth(admin)
            ).json()["items"]
        ]

    assert sorted(ids({"department_id": department})) == sorted(
        [str(wanted.id), str(unverified.id)]
    )
    assert ids({"skill_id": skill}) == [str(wanted.id)]
    assert ids({"availability": "limited"}) == [str(wanted.id)]
    assert ids({"verified_only": True}) == [str(wanted.id)]


def test_researcher_detail_and_404(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    faculty = seed_user(UserRole.FACULTY)
    _make_researcher(client, admin, faculty, bio="Studies optics.")

    detail = client.get(f"/api/v1/researchers/{faculty.id}", headers=_auth(admin))
    assert detail.status_code == 200
    assert detail.json()["bio"] == "Studies optics."
    assert "email" not in detail.json()

    missing = client.get(
        "/api/v1/researchers/11111111-1111-1111-1111-111111111111", headers=_auth(admin)
    )
    assert missing.status_code == 404


def test_students_endpoint_is_forbidden_for_students(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    student = seed_user(UserRole.STUDENT)

    assert client.get("/api/v1/students", headers=_auth(student)).status_code == 403


def test_students_endpoint_only_returns_opted_in_students(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    faculty = seed_user(UserRole.FACULTY)
    opted_in = seed_user(UserRole.STUDENT)
    opted_out = seed_user(UserRole.STUDENT)
    client.put(
        "/api/v1/me/profile",
        headers=_auth(opted_in),
        json={"program": "B.Tech CSE", "year": 2, "is_discoverable": True},
    )
    client.put(
        "/api/v1/me/profile",
        headers=_auth(opted_out),
        json={"program": "B.Tech CSE", "year": 2, "is_discoverable": False},
    )

    response = client.get("/api/v1/students", headers=_auth(faculty))

    assert response.status_code == 200
    ids = [item["user_id"] for item in response.json()["items"]]
    assert ids == [str(opted_in.id)]
    assert "email" not in response.json()["items"][0]


def test_students_endpoint_is_allowed_for_coordinator_and_admin(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)
    admin = seed_user(UserRole.ADMIN)

    assert client.get("/api/v1/students", headers=_auth(coordinator)).status_code == 200
    assert client.get("/api/v1/students", headers=_auth(admin)).status_code == 200


def test_pagination_cap_is_enforced(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)

    response = client.get("/api/v1/researchers", params={"page_size": 500}, headers=_auth(admin))

    assert response.status_code == 422


def test_unified_search_returns_researchers(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    faculty = seed_user(UserRole.FACULTY)
    skill = _skill(client, admin, "Photonics")
    _make_researcher(client, admin, faculty, skill_ids=[skill])

    response = client.get("/api/v1/search", params={"q": "photonics"}, headers=_auth(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "photonics"
    assert [r["user_id"] for r in body["researchers"]] == [str(faculty.id)]


def test_search_document_refreshes_when_skills_change(
    client: TestClient, seed_user: Callable[..., SeededUser]
) -> None:
    admin = seed_user(UserRole.ADMIN)
    faculty = seed_user(UserRole.FACULTY)
    old_skill = _skill(client, admin, "Fortran")
    new_skill = _skill(client, admin, "Haskell")
    _make_researcher(client, admin, faculty, skill_ids=[old_skill])

    client.put(
        "/api/v1/me/skills",
        headers=_auth(faculty),
        json=[{"skill_id": new_skill, "proficiency": 3}],
    )

    def hits(term: str) -> int:
        return int(
            client.get("/api/v1/researchers", params={"q": term}, headers=_auth(admin)).json()[
                "total"
            ]
        )

    assert hits("haskell") == 1
    assert hits("fortran") == 0
