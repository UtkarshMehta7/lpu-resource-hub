"""Natural-language search, mounted under /api/v1.

`semantic_used` is part of the response on purpose: when the optional ML
extra isn't installed the endpoint still answers, with the lexical ranking
alone, and says so rather than pretending.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rate_limit import enforce_search_rate_limit
from app.db.session import get_db
from app.modules.opportunities.schemas import OpportunityCard
from app.modules.projects.schemas import ProjectCard
from app.modules.publications.schemas import PublicationRead
from app.modules.researchers.search_schemas import ResearcherCard
from app.modules.search.hybrid import hybrid_search
from app.modules.users.models import User

router = APIRouter(tags=["search"])


class SemanticSearchResults(BaseModel):
    query: str
    # False means the answer is lexical-only (ML extra not installed).
    semantic_used: bool
    researchers: list[ResearcherCard]
    projects: list[ProjectCard]
    publications: list[PublicationRead]
    opportunities: list[OpportunityCard]


@router.get(
    "/search/semantic",
    response_model=SemanticSearchResults,
    dependencies=[Depends(enforce_search_rate_limit)],
)
def semantic_search(
    db: Annotated[Session, Depends(get_db)],
    viewer: Annotated[User, Depends(get_current_user)],
    q: str,
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> SemanticSearchResults:
    """Ask in plain language, e.g. 'researchers working on soil sensing'."""
    researchers, projects, publications, opportunities, semantic_used = hybrid_search(
        db, viewer, q, limit
    )
    return SemanticSearchResults(
        query=q,
        semantic_used=semantic_used,
        researchers=researchers,
        projects=projects,
        publications=publications,
        opportunities=opportunities,
    )
