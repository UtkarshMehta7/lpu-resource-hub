"""Recommendation responses. Cards are the same shapes the list endpoints
return, so the frontend can reuse its components."""

from __future__ import annotations

import uuid
from enum import StrEnum

from pydantic import BaseModel

from app.modules.opportunities.schemas import OpportunityCard
from app.modules.projects.schemas import ProjectCard
from app.modules.researchers.search_schemas import ResearcherCard, StudentCard


class TargetType(StrEnum):
    RESEARCHERS = "researchers"
    PROJECTS = "projects"
    OPPORTUNITIES = "opportunities"
    COLLABORATORS = "collaborators"


RecommendedItem = ResearcherCard | StudentCard | ProjectCard | OpportunityCard


class Recommendation(BaseModel):
    item_id: uuid.UUID
    score: float
    # Every reason is derived from a score component that actually
    # contributed (app/ml/explain.py); nothing here is generated prose.
    reasons: list[str]
    item: RecommendedItem


class RecommendationsResponse(BaseModel):
    type: TargetType
    # True when the viewer's profile is too sparse to rank on, so these are
    # simply the newest items.
    cold_start: bool
    items: list[Recommendation]
