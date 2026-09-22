"""Schemas for saved items.

Separate from profiles/schemas.py because the entries embed cards from the
researchers module, which itself imports profiles/schemas.py -- keeping
them apart avoids a circular import.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, model_validator

from app.modules.opportunities.schemas import OpportunityCard
from app.modules.projects.schemas import ProjectCard
from app.modules.researchers.search_schemas import ResearcherCard


class SavedType(StrEnum):
    PROJECT = "project"
    OPPORTUNITY = "opportunity"
    RESEARCHER = "researcher"


class SavedCreate(BaseModel):
    project_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    researcher_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        targets = (self.project_id, self.opportunity_id, self.researcher_id)
        if sum(target is not None for target in targets) != 1:
            raise ValueError("save exactly one of project_id, opportunity_id or researcher_id")
        return self


class SavedEntry(BaseModel):
    id: uuid.UUID
    saved_type: SavedType
    created_at: datetime
    item: ProjectCard | OpportunityCard | ResearcherCard
