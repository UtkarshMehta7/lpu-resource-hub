"""Application factory, OpenAPI, error envelope and CORS."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import TEST_ORIGIN, make_settings


def test_create_app_builds_application(app: FastAPI) -> None:
    assert isinstance(app, FastAPI)
    assert app.title == "LPU Research Intelligence & Collaboration Hub"


def test_openapi_schema_lists_health_routes(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/health" in paths
    assert "/health/ready" in paths


def test_docs_disabled_in_production() -> None:
    production = make_settings(app_env="production", cors_origins="https://hub.example.org")
    client = TestClient(create_app(production))

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "details": None}
    }


def test_cors_preflight_allows_configured_origin(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={"Origin": TEST_ORIGIN, "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == TEST_ORIGIN


def test_cors_preflight_rejects_foreign_origin(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
