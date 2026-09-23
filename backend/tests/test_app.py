"""Application factory, OpenAPI, error envelope and CORS."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Environment, Settings
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


def test_cors_preflight_allows_the_csrf_header(client: TestClient) -> None:
    """Every browser request carries X-Requested-With (the CSRF guard), so a
    preflight that asks for it must succeed -- otherwise the whole frontend
    fails with a network error."""
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": TEST_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-requested-with",
        },
    )

    assert response.status_code == 200
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "x-requested-with" in allowed


def test_cors_preflight_rejects_foreign_origin(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_security_headers_are_sent_on_every_response(client: TestClient) -> None:
    """Including on errors -- the middleware wraps the exception handlers."""
    for response in (client.get("/health"), client.get("/api/v1/does-not-exist")):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "geolocation=()" in response.headers["permissions-policy"]


def test_api_content_security_policy_denies_everything(client: TestClient) -> None:
    """This service answers JSON: nothing should load, run or frame it."""
    policy = client.get("/health").headers["content-security-policy"]

    assert "default-src 'none'" in policy
    assert "frame-ancestors 'none'" in policy


def test_hsts_is_production_only(db_settings: Settings) -> None:
    """Sending HSTS in development would pin localhost to HTTPS in the
    developer's own browser."""
    development = db_settings.model_copy(update={"app_env": Environment.DEVELOPMENT})
    production = db_settings.model_copy(update={"app_env": Environment.PRODUCTION})

    with TestClient(create_app(development)) as client:
        assert "strict-transport-security" not in client.get("/health").headers
    with TestClient(create_app(production)) as client:
        assert client.get("/health").headers["strict-transport-security"].startswith("max-age=")
