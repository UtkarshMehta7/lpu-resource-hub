"""'This opportunity looks relevant to you' notifications.

Reuses the Step 9 scoring, so a notification and a recommendation can never
disagree about the same opening -- and the reasons shown come from the score
breakdown, exactly as on the recommendations page. Only people whose score
clears a threshold hear about it, and only once per opening.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ml.explain import build_reasons
from app.ml.scoring import score_item
from app.modules.notifications.models import NotificationType
from app.modules.notifications.service import notify
from app.modules.opportunities.models import STUDENT_TYPES, Opportunity, OpportunityType
from app.modules.profiles.models import UserResearchArea, UserSkill
from app.modules.recommendations.service import (
    area_parents,
    opportunity_features,
    tag_names,
    viewer_features,
)
from app.modules.recommendations.weights import score_weights
from app.modules.users.models import User, UserRole

# Don't notify half a department because one word matched.
MIN_SCORE = 0.35
# A published opening can't fan out unboundedly.
MAX_RECIPIENTS = 50
# Below this many tags there is nothing to match on (same bar as cold start).
MIN_TAGS = 3


def _eligible_roles(opportunity: Opportunity) -> tuple[UserRole, ...]:
    if opportunity.opportunity_type in STUDENT_TYPES:
        return (UserRole.STUDENT,)
    if opportunity.opportunity_type is OpportunityType.COLLABORATION:
        return (UserRole.FACULTY, UserRole.RESEARCH_COORDINATOR)
    return ()


def notify_relevant_users(db: Session, opportunity_id: uuid.UUID | str) -> int:
    """Notifies eligible users whose profile matches the opening.

    Returns how many notifications were written.
    """
    opportunity = db.get(Opportunity, uuid.UUID(str(opportunity_id)))
    if opportunity is None:
        return 0
    roles = _eligible_roles(opportunity)
    if not roles:
        return 0

    enough_skills = (
        select(UserSkill.user_id).group_by(UserSkill.user_id).having(func.count() >= MIN_TAGS)
    )
    enough_areas = (
        select(UserResearchArea.user_id)
        .group_by(UserResearchArea.user_id)
        .having(func.count() >= MIN_TAGS)
    )
    candidates = list(
        db.execute(
            select(User).where(
                User.is_active.is_(True),
                User.role.in_(roles),
                User.id != opportunity.created_by,
                User.id.in_(enough_skills) | User.id.in_(enough_areas),
            )
        ).scalars()
    )
    if not candidates:
        return 0

    weights = score_weights(get_settings())
    item = opportunity_features(db, opportunity)
    parents = area_parents(db)
    skill_names, area_names = tag_names(db)

    sent = 0
    for candidate in candidates:
        if sent >= MAX_RECIPIENTS:
            break
        breakdown = score_item(viewer_features(db, candidate), item, parents, weights)
        if breakdown.score < MIN_SCORE:
            continue
        created = notify(
            db,
            user_id=candidate.id,
            notification_type=NotificationType.RELEVANT_OPPORTUNITY,
            payload={
                "opportunity_id": str(opportunity.id),
                "opportunity_title": opportunity.title,
                "score": round(breakdown.score, 4),
                "reasons": build_reasons(breakdown, skill_names, area_names),
            },
            # One "this is relevant" per opening per person, ever.
            dedupe_key=f"relevant-opportunity:{opportunity.id}",
        )
        if created is not None:
            sent += 1
    return sent
