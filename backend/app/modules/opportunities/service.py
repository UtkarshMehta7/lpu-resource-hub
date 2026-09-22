"""Opportunities: create on an ACTIVE project (or within a coordinator's
department), publish, edit, close, list. Services never import FastAPI."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.events import EVENT_BUS, Event, EventName
from app.core.pagination import Page, PageParams
from app.modules.applications.models import Application, ApplicationStatus
from app.modules.audit import service as audit_service
from app.modules.opportunities.models import (
    Opportunity,
    OpportunitySkill,
    OpportunityStatus,
    OpportunityType,
)
from app.modules.opportunities.policies import (
    EDITABLE_STATUSES,
    Actor,
    InvalidTransitionError,
    NotOwnerError,
    actor_for,
    assert_transition,
    coordinator_department,
    visibility_filter,
)
from app.modules.opportunities.schemas import (
    OpportunityCard,
    OpportunityCreate,
    OpportunityRead,
    OpportunityUpdate,
    SkillRequirement,
    SkillTag,
)
from app.modules.projects.models import Project, ProjectStatus
from app.modules.projects.policies import visibility_filter as project_visibility
from app.modules.taxonomy.models import Skill
from app.modules.users.models import User, UserRole


class OpportunityNotFoundError(Exception):
    """No such opportunity, or the viewer may not know it exists."""


class ProjectRequiredError(Exception):
    """Faculty must attach an opportunity to one of their projects."""


class ProjectNotFoundError(Exception):
    """The project doesn't exist or isn't visible to the caller."""


class NotProjectOwnerError(Exception):
    """The caller can't post openings on this project."""


class ProjectNotActiveError(Exception):
    """Openings can only be posted on (and published for) ACTIVE projects."""


class UnknownSkillError(Exception):
    """One or more skill ids don't exist."""


class InvalidDeadlineError(Exception):
    """A new or edited deadline is in the past (bad input)."""


class DeadlinePassedError(Exception):
    """The deadline has passed, so the action is no longer possible."""


class PositionsBelowAcceptedError(Exception):
    """positions can't drop below the number of already-accepted applicants."""


def today() -> date:
    return datetime.now(UTC).date()


# --- helpers -----------------------------------------------------------------


def load_visible(db: Session, viewer: User, opportunity_id: uuid.UUID) -> Opportunity:
    opportunity = db.execute(
        select(Opportunity).where(Opportunity.id == opportunity_id, visibility_filter(viewer))
    ).scalar_one_or_none()
    if opportunity is None:
        raise OpportunityNotFoundError
    return opportunity


def accepted_count(db: Session, opportunity_id: uuid.UUID) -> int:
    return db.execute(
        select(func.count()).where(
            Application.opportunity_id == opportunity_id,
            Application.status == ApplicationStatus.ACCEPTED,
        )
    ).scalar_one()


def _validate_skills(db: Session, skills: Sequence[SkillRequirement]) -> None:
    ids = {s.skill_id for s in skills}
    if not ids:
        return
    found = set(db.execute(select(Skill.id).where(Skill.id.in_(ids))).scalars())
    if ids - found:
        raise UnknownSkillError


def _replace_skills(
    db: Session, opportunity_id: uuid.UUID, skills: Sequence[SkillRequirement]
) -> None:
    db.execute(delete(OpportunitySkill).where(OpportunitySkill.opportunity_id == opportunity_id))
    unique = {s.skill_id: s.is_required for s in skills}
    db.add_all(
        OpportunitySkill(opportunity_id=opportunity_id, skill_id=sid, is_required=required)
        for sid, required in unique.items()
    )


def _resolve_project(db: Session, actor: User, project_id: uuid.UUID) -> Project:
    project = db.execute(
        select(Project).where(
            Project.id == project_id, Project.deleted_at.is_(None), project_visibility(actor)
        )
    ).scalar_one_or_none()
    if project is None:
        raise ProjectNotFoundError
    scope = coordinator_department(actor)
    in_scope = scope is not None and scope == project.department_id
    if project.owner_id != actor.id and not in_scope:
        raise NotProjectOwnerError
    if project.status is not ProjectStatus.ACTIVE:
        raise ProjectNotActiveError
    return project


def _to_cards(db: Session, viewer: User, rows: Sequence[Opportunity]) -> list[OpportunityCard]:
    if not rows:
        return []
    ids = [o.id for o in rows]
    skills: dict[uuid.UUID, list[SkillTag]] = {i: [] for i in ids}
    for opp_id, sid, name, required in db.execute(
        select(OpportunitySkill.opportunity_id, Skill.id, Skill.name, OpportunitySkill.is_required)
        .join(Skill, Skill.id == OpportunitySkill.skill_id)
        .where(OpportunitySkill.opportunity_id.in_(ids))
        .order_by(OpportunitySkill.is_required.desc(), Skill.name)
    ).all():
        skills[opp_id].append(SkillTag(id=sid, name=name, is_required=required))

    creators: dict[uuid.UUID, str] = {
        uid: name
        for uid, name in db.execute(
            select(User.id, User.full_name).where(User.id.in_({o.created_by for o in rows}))
        ).all()
    }
    project_ids = {o.project_id for o in rows if o.project_id is not None}
    projects: dict[uuid.UUID, str] = {}
    if project_ids:
        projects = {
            pid: title
            for pid, title in db.execute(
                select(Project.id, Project.title).where(
                    Project.id.in_(project_ids),
                    Project.deleted_at.is_(None),
                    project_visibility(viewer),
                )
            ).all()
        }
    accepted: dict[uuid.UUID, int] = {
        oid: count
        for oid, count in db.execute(
            select(Application.opportunity_id, func.count())
            .where(
                Application.opportunity_id.in_(ids),
                Application.status == ApplicationStatus.ACCEPTED,
            )
            .group_by(Application.opportunity_id)
        ).all()
    }
    return [
        OpportunityCard(
            id=o.id,
            title=o.title,
            opportunity_type=o.opportunity_type,
            status=o.status,
            project_id=o.project_id,
            project_title=projects.get(o.project_id) if o.project_id else None,
            department_id=o.department_id,
            created_by=o.created_by,
            creator_name=creators.get(o.created_by, ""),
            positions=o.positions,
            accepted_count=accepted.get(o.id, 0),
            deadline=o.deadline,
            skills=skills[o.id],
        )
        for o in rows
    ]


def opportunity_cards(
    db: Session, viewer: User, rows: Sequence[Opportunity]
) -> list[OpportunityCard]:
    """Public wrapper used by recommendations (Step 9)."""
    return _to_cards(db, viewer, rows)


def to_read(db: Session, viewer: User, opportunity: Opportunity) -> OpportunityRead:
    card = _to_cards(db, viewer, [opportunity])[0]
    mine = db.execute(
        select(Application.id).where(
            Application.opportunity_id == opportunity.id, Application.applicant_id == viewer.id
        )
    ).scalar_one_or_none()
    return OpportunityRead(
        **card.model_dump(),
        description=opportunity.description,
        eligibility=opportunity.eligibility,
        created_at=opportunity.created_at,
        updated_at=opportunity.updated_at,
        my_application_id=mine,
    )


# --- operations --------------------------------------------------------------


def create_opportunity(db: Session, actor: User, data: OpportunityCreate) -> OpportunityRead:
    if data.deadline < today():
        raise InvalidDeadlineError
    _validate_skills(db, data.skills)
    if data.project_id is not None:
        project = _resolve_project(db, actor, data.project_id)
        department_id = project.department_id
    elif actor.role is UserRole.RESEARCH_COORDINATOR:
        # A department-wide opening, not tied to one project.
        department_id = coordinator_department(actor) or actor.department_id
    else:
        raise ProjectRequiredError

    opportunity = Opportunity(
        title=data.title,
        description=data.description,
        opportunity_type=data.opportunity_type,
        project_id=data.project_id,
        created_by=actor.id,
        department_id=department_id,
        eligibility=data.eligibility,
        positions=data.positions,
        deadline=data.deadline,
    )
    db.add(opportunity)
    db.flush()
    _replace_skills(db, opportunity.id, data.skills)
    db.commit()
    db.refresh(opportunity)
    return to_read(db, actor, opportunity)


def get_opportunity(db: Session, viewer: User, opportunity_id: uuid.UUID) -> OpportunityRead:
    return to_read(db, viewer, load_visible(db, viewer, opportunity_id))


def update_opportunity(
    db: Session, actor: User, opportunity_id: uuid.UUID, data: OpportunityUpdate
) -> OpportunityRead:
    opportunity = load_visible(db, actor, opportunity_id)
    if opportunity.created_by != actor.id:
        raise NotOwnerError
    if opportunity.status not in EDITABLE_STATUSES:
        raise InvalidTransitionError
    if data.deadline is not None and data.deadline < today():
        raise InvalidDeadlineError
    if data.positions is not None and data.positions < accepted_count(db, opportunity.id):
        raise PositionsBelowAcceptedError
    if data.skills is not None:
        _validate_skills(db, data.skills)

    for field in ("title", "description", "opportunity_type", "positions", "deadline"):
        value = getattr(data, field)
        if value is not None:
            setattr(opportunity, field, value)
    if "eligibility" in data.model_fields_set:
        opportunity.eligibility = data.eligibility
    if data.skills is not None:
        _replace_skills(db, opportunity.id, data.skills)
    db.commit()
    db.refresh(opportunity)
    return to_read(db, actor, opportunity)


def _actor_or_forbidden(user: User, opportunity: Opportunity) -> Actor:
    actor = actor_for(user, opportunity)
    if actor is None:
        raise NotOwnerError
    return actor


def publish_opportunity(db: Session, user: User, opportunity_id: uuid.UUID) -> OpportunityRead:
    opportunity = load_visible(db, user, opportunity_id)
    assert_transition(
        opportunity.status, OpportunityStatus.OPEN, _actor_or_forbidden(user, opportunity)
    )
    if opportunity.deadline < today():
        raise DeadlinePassedError
    if opportunity.project_id is not None:
        project = db.get(Project, opportunity.project_id)
        if project is None or project.status is not ProjectStatus.ACTIVE:
            raise ProjectNotActiveError
    opportunity.status = OpportunityStatus.OPEN
    db.flush()
    # Tells people whose profile matches (Step 12); scored with the same code
    # as the recommendations page.
    EVENT_BUS.publish(
        db,
        Event(
            name=EventName.OPPORTUNITY_PUBLISHED,
            actor_id=user.id,
            payload={"opportunity_id": opportunity.id},
        ),
    )
    db.commit()
    db.refresh(opportunity)
    return to_read(db, user, opportunity)


def close_opportunity(
    db: Session, user: User, opportunity_id: uuid.UUID, *, ip: str | None
) -> OpportunityRead:
    opportunity = load_visible(db, user, opportunity_id)
    actor = _actor_or_forbidden(user, opportunity)
    assert_transition(opportunity.status, OpportunityStatus.CLOSED, actor)
    before = opportunity.status.value
    opportunity.status = OpportunityStatus.CLOSED
    if actor != "owner":
        audit_service.record(
            db,
            actor_id=user.id,
            action="opportunity.closed",
            entity_type="opportunity",
            entity_id=opportunity.id,
            before={"status": before},
            after={"status": OpportunityStatus.CLOSED.value},
            ip=ip,
        )
    db.commit()
    db.refresh(opportunity)
    return to_read(db, user, opportunity)


def mark_filled_if_full(db: Session, opportunity: Opportunity) -> None:
    """Called inside the accept transaction; FILLED is a system transition."""
    if (
        opportunity.status is OpportunityStatus.OPEN
        and accepted_count(db, opportunity.id) >= opportunity.positions
    ):
        assert_transition(opportunity.status, OpportunityStatus.FILLED, "system")
        opportunity.status = OpportunityStatus.FILLED


def list_opportunities(
    db: Session,
    viewer: User,
    params: PageParams,
    *,
    q: str | None = None,
    opportunity_type: OpportunityType | None = None,
    status: OpportunityStatus | None = None,
    department_id: uuid.UUID | None = None,
    skill_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    deadline_after: date | None = None,
    deadline_before: date | None = None,
    mine: bool = False,
) -> Page[OpportunityCard]:
    query = select(Opportunity).where(visibility_filter(viewer))
    tsquery = func.websearch_to_tsquery("english", q) if q else None
    if tsquery is not None:
        query = query.where(Opportunity.search_document.op("@@")(tsquery))
    if opportunity_type is not None:
        query = query.where(Opportunity.opportunity_type == opportunity_type)
    if status is not None:
        query = query.where(Opportunity.status == status)
    if department_id is not None:
        query = query.where(Opportunity.department_id == department_id)
    if project_id is not None:
        query = query.where(Opportunity.project_id == project_id)
    if skill_id is not None:
        query = query.where(
            Opportunity.id.in_(
                select(OpportunitySkill.opportunity_id).where(OpportunitySkill.skill_id == skill_id)
            )
        )
    if deadline_after is not None:
        query = query.where(Opportunity.deadline >= deadline_after)
    if deadline_before is not None:
        query = query.where(Opportunity.deadline <= deadline_before)
    if mine:
        query = query.where(Opportunity.created_by == viewer.id)

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    if tsquery is not None:
        query = query.order_by(func.ts_rank(Opportunity.search_document, tsquery).desc())
    query = query.order_by(Opportunity.deadline, Opportunity.title)
    rows = db.execute(query.offset(params.offset).limit(params.page_size)).scalars().all()
    return Page[OpportunityCard](
        items=_to_cards(db, viewer, rows),
        page=params.page,
        page_size=params.page_size,
        total=total,
    )
