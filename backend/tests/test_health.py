"""Health endpoints. The database check is stubbed; see test_database.py for the real one."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.modules.health.router import DatabaseCheck, get_database_check


def _healthy() -> None:
    return None


def _unreachable() -> None:
    raise OperationalError("SELECT 1", {}, ConnectionRefusedError("connection refused"))


def _use_check(app: FastAPI, check: DatabaseCheck) -> None:
    app.dependency_overrides[get_database_check] = lambda: check


def test_liveness_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_liveness_does_not_touch_the_database(app: FastAPI, client: TestClient) -> None:
    _use_check(app, _unreachable)

    assert client.get("/health").status_code == 200


def test_readiness_ok_when_database_reachable(app: FastAPI, client: TestClient) -> None:
    _use_check(app, _healthy)

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_readiness_503_when_database_unreachable(app: FastAPI, client: TestClient) -> None:
    _use_check(app, _unreachable)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}
