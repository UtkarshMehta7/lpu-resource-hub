"""Liveness and readiness probes.

* ``GET /health`` - liveness. Never touches dependencies, so it stays fast and
  only fails if the process itself is broken.
* ``GET /health/ready`` - readiness. Verifies the full chain down to PostgreSQL
  and returns 503 when the database is unreachable.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import check_database_connection, get_engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

DatabaseCheck = Callable[[], None]


class LivenessResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]


def get_database_check(engine: Annotated[Engine, Depends(get_engine)]) -> DatabaseCheck:
    """Dependency returning the readiness check; overridable in tests."""
    return lambda: check_database_connection(engine)


@router.get("/health", response_model=LivenessResponse)
def health() -> LivenessResponse:
    return LivenessResponse(status="ok")


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
def readiness(
    response: Response,
    check_database: Annotated[DatabaseCheck, Depends(get_database_check)],
) -> ReadinessResponse:
    try:
        check_database()
    except SQLAlchemyError as exc:
        logger.warning(
            "Readiness check failed, database unavailable: %s", getattr(exc, "orig", exc)
        )
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="degraded", database="unavailable")
    return ReadinessResponse(status="ok", database="ok")
