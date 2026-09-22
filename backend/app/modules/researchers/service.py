"""Researcher verification: queue + decision. Services never import FastAPI."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.events import EVENT_BUS, Event, EventName
from app.modules.audit import service as audit_service
from app.modules.profiles.models import ResearcherProfile, VerificationStatus
from app.modules.researchers.policies import (
    assert_in_coordinator_scope,
    assert_not_self_verification,
)
from app.modules.researchers.schemas import VerificationQueueItem
from app.modules.users.models import CoordinatorScopeType, User, UserRole


class ResearcherNotFoundError(Exception):
    """Raised when the target user has no researcher profile."""


def to_queue_item(user: User, profile: ResearcherProfile) -> VerificationQueueItem:
    return VerificationQueueItem(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        designation=profile.designation,
        department_id=user.department_id,
        verification_status=profile.verification_status,
        created_at=profile.created_at,
    )


def list_verification_queue(db: Session, reviewer: User) -> list[tuple[User, ResearcherProfile]]:
    query = (
        select(User, ResearcherProfile)
        .join(ResearcherProfile, ResearcherProfile.user_id == User.id)
        .where(ResearcherProfile.verification_status == VerificationStatus.PENDING)
    )
    if reviewer.role is UserRole.RESEARCH_COORDINATOR:
        if (
            reviewer.coordinator_scope_type is not CoordinatorScopeType.DEPARTMENT
            or reviewer.coordinator_scope_id is None
        ):
            return []
        query = query.where(User.department_id == reviewer.coordinator_scope_id)

    rows = db.execute(query.order_by(ResearcherProfile.created_at)).all()
    return [(row[0], row[1]) for row in rows]


def _load_researcher(db: Session, user_id: uuid.UUID) -> tuple[User, ResearcherProfile]:
    row = db.execute(
        select(User, ResearcherProfile)
        .join(ResearcherProfile, ResearcherProfile.user_id == User.id)
        .where(User.id == user_id)
    ).first()
    if row is None:
        raise ResearcherNotFoundError
    return row[0], row[1]


def verify_researcher(
    db: Session,
    reviewer: User,
    target_user_id: uuid.UUID,
    decision: VerificationStatus,
    *,
    comment: str | None = None,
    ip: str | None,
) -> tuple[User, ResearcherProfile]:
    target_user, profile = _load_researcher(db, target_user_id)

    assert_not_self_verification(reviewer, target_user)
    assert_in_coordinator_scope(reviewer, target_user)

    before = {"verification_status": profile.verification_status.value}
    profile.verification_status = decision
    profile.verified_by = reviewer.id
    profile.verified_at = datetime.now(UTC)
    db.flush()
    EVENT_BUS.publish(
        db,
        Event(
            name=EventName.PROFILE_VERIFIED,
            actor_id=reviewer.id,
            payload={
                "recipient_id": profile.user_id,
                "status": decision.value,
                "comment": comment,
            },
        ),
    )

    # researcher_profiles has no comment column by design (see ADR 0004):
    # the reviewer's reasoning lives in the audit record, which is where the
    # rest of the decision's provenance already is.
    audit_service.record(
        db,
        actor_id=reviewer.id,
        action="profile.verified",
        entity_type="researcher_profile",
        entity_id=target_user.id,
        before=before,
        after={"verification_status": profile.verification_status.value, "comment": comment},
        ip=ip,
    )
    db.commit()
    db.refresh(profile)
    return target_user, profile
