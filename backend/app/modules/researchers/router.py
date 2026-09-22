"""Researcher verification endpoints.

A coordinator acting outside their department scope gets 404, not 403: per
docs/architecture.md §6, they must not learn the profile exists at all.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.pagination import Page, PageParams
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import client_ip, enforce_search_rate_limit
from app.db.session import get_db
from app.modules.profiles.models import (
    ResearcherAvailability,
    ResearcherProfile,
    VerificationStatus,
)
from app.modules.projects.service import list_projects
from app.modules.researchers.directory import (
    ResearcherNotFoundError as DirectoryResearcherNotFoundError,
)
from app.modules.researchers.directory import (
    SortOption,
    get_researcher,
    list_discoverable_students,
    list_researchers,
)
from app.modules.researchers.policies import OutOfScopeError, SelfVerificationError
from app.modules.researchers.schemas import VerificationQueueItem, VerifyDecisionRequest
from app.modules.researchers.search_schemas import (
    ResearcherCard,
    ResearcherDetail,
    SearchResults,
    StudentCard,
)
from app.modules.researchers.service import (
    ResearcherNotFoundError,
    list_verification_queue,
    verify_researcher,
)
from app.modules.users.models import User

router = APIRouter(tags=["researchers"])


def _to_queue_item(user: User, profile: ResearcherProfile) -> VerificationQueueItem:
    return VerificationQueueItem(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        designation=profile.designation,
        department_id=user.department_id,
        verification_status=profile.verification_status,
        created_at=profile.created_at,
    )


@router.get(
    "/coordinator/verification-queue",
    response_model=list[VerificationQueueItem],
    dependencies=[Depends(require_permission(Permission.PROFILE_VERIFY))],
)
def read_verification_queue(
    db: Annotated[Session, Depends(get_db)],
    reviewer: Annotated[User, Depends(get_current_user)],
) -> list[VerificationQueueItem]:
    queue = list_verification_queue(db, reviewer)
    return [_to_queue_item(user, profile) for user, profile in queue]


@router.post("/researchers/{user_id}/verify", response_model=VerificationQueueItem)
def verify_researcher_route(
    user_id: uuid.UUID,
    data: VerifyDecisionRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    reviewer: Annotated[User, Depends(require_permission(Permission.PROFILE_VERIFY))],
) -> VerificationQueueItem:
    try:
        target_user, profile = verify_researcher(
            db,
            reviewer,
            user_id,
            VerificationStatus(data.decision),
            comment=data.comment,
            ip=client_ip(request),
        )
    except (ResearcherNotFoundError, OutOfScopeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Researcher not found."
        ) from exc
    except SelfVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="You cannot verify your own profile."
        ) from exc

    return _to_queue_item(target_user, profile)


@router.get(
    "/researchers",
    response_model=Page[ResearcherCard],
    dependencies=[Depends(get_current_user), Depends(enforce_search_rate_limit)],
)
def read_researchers(
    db: Annotated[Session, Depends(get_db)],
    params: Annotated[PageParams, Depends()],
    q: str | None = None,
    school_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    research_area_id: uuid.UUID | None = None,
    skill_id: uuid.UUID | None = None,
    availability: ResearcherAvailability | None = None,
    verified_only: bool = False,
    sort: SortOption = "name",
) -> Page[ResearcherCard]:
    return list_researchers(
        db,
        params,
        q=q,
        school_id=school_id,
        department_id=department_id,
        research_area_id=research_area_id,
        skill_id=skill_id,
        availability=availability,
        verified_only=verified_only,
        sort=sort,
    )


@router.get(
    "/researchers/{user_id}",
    response_model=ResearcherDetail,
    dependencies=[Depends(get_current_user)],
)
def read_researcher(
    user_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]
) -> ResearcherDetail:
    try:
        return get_researcher(db, user_id)
    except DirectoryResearcherNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Researcher not found."
        ) from exc


@router.get(
    "/students",
    response_model=Page[StudentCard],
    dependencies=[
        Depends(require_permission(Permission.STUDENT_DISCOVER)),
        Depends(enforce_search_rate_limit),
    ],
)
def read_discoverable_students(
    db: Annotated[Session, Depends(get_db)],
    params: Annotated[PageParams, Depends()],
    q: str | None = None,
    department_id: uuid.UUID | None = None,
) -> Page[StudentCard]:
    """Faculty and above only, and only students who opted in."""
    return list_discoverable_students(db, params, q=q, department_id=department_id)


@router.get(
    "/search",
    response_model=SearchResults,
    dependencies=[Depends(get_current_user), Depends(enforce_search_rate_limit)],
)
def unified_search(
    db: Annotated[Session, Depends(get_db)],
    viewer: Annotated[User, Depends(get_current_user)],
    params: Annotated[PageParams, Depends()],
    q: str,
    types: str = "researchers,projects",
) -> SearchResults:
    """Unified search. Only researchers are searchable today; later steps add
    projects, publications and opportunities behind the same `types` filter."""
    wanted = {t.strip() for t in types.split(",") if t.strip()}
    researchers = list_researchers(db, params, q=q).items if "researchers" in wanted else []
    # Projects go through the same visibility filter as /projects, so search
    # can never surface someone else's draft.
    projects = list_projects(db, viewer, params, q=q).items if "projects" in wanted else []
    return SearchResults(query=q, researchers=researchers, projects=projects)
