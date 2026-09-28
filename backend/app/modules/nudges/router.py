"""The nudge endpoint, mounted under /api/v1.

One route. Whether the caller may nudge, and who hears about it, is decided
entirely in the service from the thing being nudged about -- there is no
recipient in the request, because letting the sender choose who to notify
would be a way to message anyone in the institution.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rate_limit import enforce_collaboration_rate_limit
from app.db.session import get_db
from app.modules.nudges import service
from app.modules.nudges.schemas import NudgeRead, NudgeRequest
from app.modules.users.models import User

router = APIRouter(tags=["nudges"])

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("/nudges", response_model=NudgeRead, status_code=status.HTTP_201_CREATED)
def send_nudge(
    request: Request, payload: NudgeRequest, db: DbSession, current_user: CurrentUser
) -> NudgeRead:
    """Remind whoever must act that something of yours is still waiting."""
    # Shares the collaboration budget: both are "this account is generating
    # notifications for other people", and that is the thing worth capping.
    enforce_collaboration_rate_limit(request, current_user.id)
    try:
        result = service.send(db, current_user, payload.kind, payload.entity_id)
    except service.NothingToNudgeAboutError as exc:
        # 404 rather than 403: the caller should not learn whether somebody
        # else's project exists by nudging about it.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="There is nothing of yours waiting on anyone here.",
        ) from exc
    except service.NudgeTooSoonError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "You nudged about this recently. You can do it again after "
                f"{exc.retry_after.strftime('%d %b %H:%M UTC')}."
            ),
        ) from exc
    except service.NoRecipientError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nobody is currently able to act on this. Contact your department office.",
        ) from exc
    return NudgeRead.model_validate(result)


__all__ = ["router"]
