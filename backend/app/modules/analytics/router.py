"""Dashboard endpoint, mounted under /api/v1."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.ml.features import ScoreWeights
from app.modules.analytics import service
from app.modules.analytics.schemas import DashboardResponse
from app.modules.users.models import User

router = APIRouter(tags=["dashboard"])


@router.get("/me/dashboard", response_model=DashboardResponse)
def read_dashboard(
    db: Annotated[Session, Depends(get_db)],
    viewer: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DashboardResponse:
    weights = ScoreWeights(
        skill=settings.rec_weight_skill,
        area=settings.rec_weight_area,
        text=settings.rec_weight_text,
    )
    return service.dashboard(db, viewer, weights)
