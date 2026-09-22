"""Recommendation endpoint, mounted under /api/v1."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.deps import get_current_user
from app.core.rate_limit import enforce_search_rate_limit
from app.db.session import get_db
from app.modules.recommendations import service
from app.modules.recommendations.schemas import RecommendationsResponse, TargetType
from app.modules.recommendations.weights import score_weights
from app.modules.users.models import User

router = APIRouter(tags=["recommendations"])


@router.get(
    "/recommendations",
    response_model=RecommendationsResponse,
    dependencies=[Depends(enforce_search_rate_limit)],
)
def read_recommendations(
    db: Annotated[Session, Depends(get_db)],
    viewer: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    type: TargetType = TargetType.OPPORTUNITIES,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> RecommendationsResponse:
    return service.recommend(db, viewer, type, limit, score_weights(settings))
