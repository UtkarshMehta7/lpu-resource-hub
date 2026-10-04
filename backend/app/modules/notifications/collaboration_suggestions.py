"""'You two should probably be working together' notifications.

The specification asks for a collaboration suggestion notification beside the
funding, milestone, booking, opening and verification ones. This is that, and
it leans on the same scoring the recommendations page uses rather than
inventing a second opinion -- so a suggestion in somebody's inbox and the same
suggestion on their For you page can never disagree.

The bar is deliberately higher than for a relevant opening. An opening is
something the recipient asked to hear about by having interests; an unsolicited
"work with this person" is an interruption, and a weak one is worse than
silence. Each pairing is suggested once, ever.

What makes a suggestion worth sending is the **gap**: the candidate set
already excludes anyone the viewer has an open or accepted request with and
anyone they have co-authored with, so what is left is a collaboration the
expertise says should exist and the record says does not.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.notifications.models import NotificationType
from app.modules.notifications.service import notify
from app.modules.profiles.models import UserResearchArea, UserSkill
from app.modules.recommendations.schemas import TargetType
from app.modules.recommendations.service import recommend
from app.modules.recommendations.weights import score_weights
from app.modules.researchers.search_schemas import ResearcherCard, StudentCard
from app.modules.users.models import User, UserRole

#: Higher than the opening threshold (0.35): nobody asked for this one.
MIN_SCORE = 0.5
#: One pairing per person per run. A list of five reads as spam.
SUGGESTIONS_PER_PERSON = 1
#: An upper bound on a single pass, so the job stays a job.
MAX_RECIPIENTS = 100
#: Below this many tags there is nothing to match on, and `recommend` would
#: return its cold-start list -- newest people, which is not a suggestion.
MIN_TAGS = 3


def _taggable_people(db: Session) -> list[User]:
    """Active non-admins with enough expertise recorded to match on."""
    skills = select(UserSkill.user_id)
    areas = select(UserResearchArea.user_id)
    return list(
        db.execute(
            select(User)
            .where(
                User.is_active.is_(True),
                User.role != UserRole.ADMIN,
                User.id.in_(skills.union(areas)),
            )
            .order_by(User.created_at)
        )
        .scalars()
        .all()
    )


def _tag_count(db: Session, user: User) -> int:
    skills = db.execute(select(UserSkill.skill_id).where(UserSkill.user_id == user.id)).all()
    areas = db.execute(
        select(UserResearchArea.research_area_id).where(UserResearchArea.user_id == user.id)
    ).all()
    return len(skills) + len(areas)


def send_collaboration_suggestions(db: Session, *, limit: int = MAX_RECIPIENTS) -> int:
    """Suggest one collaborator to each person who has a strong enough match.

    Idempotent in the way that matters: the dedupe key is the ordered pair, so
    the same two people are never introduced twice however often this runs,
    and introducing A to B also stands as the introduction of B to A.
    """
    weights = score_weights(get_settings())
    sent = 0

    for viewer in _taggable_people(db):
        if sent >= limit:
            break
        if _tag_count(db, viewer) < MIN_TAGS:
            continue

        result = recommend(db, viewer, TargetType.COLLABORATORS, SUGGESTIONS_PER_PERSON, weights)
        # Cold start returns the newest people rather than a ranking; that is
        # a listing, not a suggestion, and must never be sent as one.
        if result.cold_start:
            continue

        for item in result.items:
            if item.score < MIN_SCORE:
                continue
            card = item.item
            # Collaborators are always people, but the card union covers
            # projects and openings too, so narrow rather than assume.
            if not isinstance(card, ResearcherCard | StudentCard):
                continue
            pair = sorted((str(viewer.id), str(item.item_id)))
            created = notify(
                db,
                user_id=viewer.id,
                notification_type=NotificationType.COLLABORATION_SUGGESTION,
                payload={
                    "user_id": str(item.item_id),
                    "full_name": card.full_name,
                    # Names collide; the registration number does not, and it
                    # is shown wherever a person is named.
                    "registration_number": card.registration_number,
                    "score": round(item.score, 4),
                    # Straight from the score breakdown, like every other
                    # explanation in this platform. Nothing is generated prose.
                    "reasons": item.reasons,
                },
                dedupe_key=f"collaboration-suggestion:{pair[0]}:{pair[1]}",
            )
            if created is not None:
                sent += 1
    return sent


__all__ = ["MIN_SCORE", "send_collaboration_suggestions"]
