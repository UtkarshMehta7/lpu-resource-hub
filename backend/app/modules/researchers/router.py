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
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import client_ip
from app.db.session import get_db
from app.modules.profiles.models import ResearcherProfile, VerificationStatus
from app.modules.researchers.policies import OutOfScopeError, SelfVerificationError
from app.modules.researchers.schemas import VerificationQueueItem, VerifyDecisionRequest
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
            db, reviewer, user_id, VerificationStatus(data.decision), ip=client_ip(request)
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
