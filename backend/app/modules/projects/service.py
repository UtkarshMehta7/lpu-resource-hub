"""Research projects: CRUD, workflow transitions, team members, listing.

Every read goes through policies.visibility_filter, so a project the caller
must not see is simply not found. Services never import FastAPI.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.events import EVENT_BUS, Event, EventName
from app.core.pagination import Page, PageParams
from app.modules.audit import service as audit_service
from app.modules.profiles.models import ResearcherProfile, VerificationStatus
from app.modules.projects.models import (
    Project,
    ProjectMember,
    ProjectResearchArea,
    ProjectSkill,
    ProjectStatus,
)
from app.modules.projects.policies import (
    EDITABLE_STATUSES,
    Actor,
    InvalidTransitionError,
    assert_not_own_project,
    assert_owner,
    assert_transition,
    visibility_filter,
)
from app.modules.projects.schemas import (
    MemberCreate,
    MemberRead,
    ProjectCard,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    ReviewRequest,
)
from app.modules.taxonomy.models import ResearchArea, Skill
from app.modules.users.models import CoordinatorScopeType, User, UserRole


class ProjectNotFoundError(Exception):
    """Missing, deleted, or not visible to the caller."""


class UnknownTagError(Exception):
    """A skill or research-area id in the request does not exist."""


class OwnerNotVerifiedError(Exception):
    """Only a verified researcher may submit a project for review."""


class InvalidDateRangeError(Exception):
    """After a partial update, start_date would fall after end_date."""


class MemberNotFoundError(Exception):
    """The user to add, or the member to remove, does not exist."""


class DuplicateMemberError(Exception):
    """The user is already a member of this project."""


# --- loading ---------------------------------------------------------------


def _load_visible(db: Session, viewer: User, project_id: uuid.UUID) -> Project:
    project = db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.deleted_at.is_(None),
            visibility_filter(viewer),
        )
    ).scalar_one_or_none()
    if project is None:
        raise ProjectNotFoundError
    return project


# --- tags ------------------------------------------------------------------


def _validate_tags(
    db: Session, skill_ids: Sequence[uuid.UUID], area_ids: Sequence[uuid.UUID]
) -> None:
    if skill_ids:
        found = set(db.execute(select(Skill.id).where(Skill.id.in_(skill_ids))).scalars())
        if set(skill_ids) - found:
            raise UnknownTagError
    if area_ids:
        found = set(
            db.execute(select(ResearchArea.id).where(ResearchArea.id.in_(area_ids))).scalars()
        )
        if set(area_ids) - found:
            raise UnknownTagError


def _replace_tags(
    db: Session,
    project_id: uuid.UUID,
    skill_ids: Sequence[uuid.UUID] | None,
    area_ids: Sequence[uuid.UUID] | None,
) -> None:
    if skill_ids is not None:
        db.execute(delete(ProjectSkill).where(ProjectSkill.project_id == project_id))
        db.add_all(ProjectSkill(project_id=project_id, skill_id=sid) for sid in set(skill_ids))
    if area_ids is not None:
        db.execute(delete(ProjectResearchArea).where(ProjectResearchArea.project_id == project_id))
        db.add_all(
            ProjectResearchArea(project_id=project_id, research_area_id=aid)
            for aid in set(area_ids)
        )


# --- building responses ----------------------------------------------------


def _tags_by_project(
    db: Session, project_ids: Sequence[uuid.UUID]
) -> tuple[dict[uuid.UUID, list[str]], dict[uuid.UUID, list[str]]]:
    areas: dict[uuid.UUID, list[str]] = {}
    skills: dict[uuid.UUID, list[str]] = {}
    if not project_ids:
        return areas, skills
    for pid, name in db.execute(
        select(ProjectResearchArea.project_id, ResearchArea.name)
        .join(ResearchArea, ResearchArea.id == ProjectResearchArea.research_area_id)
        .where(ProjectResearchArea.project_id.in_(project_ids))
        .order_by(ResearchArea.name)
    ):
        areas.setdefault(pid, []).append(name)
    for pid, name in db.execute(
        select(ProjectSkill.project_id, Skill.name)
        .join(Skill, Skill.id == ProjectSkill.skill_id)
        .where(ProjectSkill.project_id.in_(project_ids))
        .order_by(Skill.name)
    ):
        skills.setdefault(pid, []).append(name)
    return areas, skills


def _owner_names(db: Session, owner_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, tuple[str, str]]:
    """Name and registration number together: a name alone is ambiguous."""
    if not owner_ids:
        return {}
    return {
        row[0]: (row[1], row[2])
        for row in db.execute(
            select(User.id, User.full_name, User.registration_number).where(User.id.in_(owner_ids))
        ).all()
    }


def _to_cards(db: Session, projects: Sequence[Project]) -> list[ProjectCard]:
    ids = [p.id for p in projects]
    areas, skills = _tags_by_project(db, ids)
    owners = _owner_names(db, list({p.owner_id for p in projects}))
    return [
        ProjectCard(
            id=p.id,
            title=p.title,
            summary=p.summary,
            status=p.status,
            owner_id=p.owner_id,
            owner_name=owners.get(p.owner_id, ("", ""))[0],
            owner_registration_number=owners.get(p.owner_id, ("", ""))[1],
            department_id=p.department_id,
            start_date=p.start_date,
            end_date=p.end_date,
            research_areas=areas.get(p.id, []),
            skills=skills.get(p.id, []),
        )
        for p in projects
    ]


def _members(db: Session, project_id: uuid.UUID) -> list[MemberRead]:
    rows = db.execute(
        select(
            ProjectMember.user_id,
            User.full_name,
            User.registration_number,
            ProjectMember.member_role,
        )
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.created_at)
    ).all()
    return [
        MemberRead(user_id=uid, full_name=name, registration_number=number, member_role=role)
        for uid, name, number, role in rows
    ]


def _to_read(db: Session, project: Project) -> ProjectRead:
    card = _to_cards(db, [project])[0]
    return ProjectRead(
        **card.model_dump(),
        description=project.description,
        objectives=project.objectives,
        review_comment=project.review_comment,
        reviewed_at=project.reviewed_at,
        members=_members(db, project.id),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


# --- reads -----------------------------------------------------------------


def project_cards(db: Session, projects: Sequence[Project]) -> list[ProjectCard]:
    """Public wrapper used by recommendations (Step 9)."""
    return _to_cards(db, projects)


def get_project(db: Session, viewer: User, project_id: uuid.UUID) -> ProjectRead:
    return _to_read(db, _load_visible(db, viewer, project_id))


def list_projects(
    db: Session,
    viewer: User,
    params: PageParams,
    *,
    q: str | None = None,
    status: ProjectStatus | None = None,
    department_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    research_area_id: uuid.UUID | None = None,
    skill_id: uuid.UUID | None = None,
    mine: bool = False,
) -> Page[ProjectCard]:
    query = select(Project).where(Project.deleted_at.is_(None), visibility_filter(viewer))
    if q:
        query = query.where(
            Project.search_document.op("@@")(func.websearch_to_tsquery("english", q))
        )
    if status is not None:
        query = query.where(Project.status == status)
    if department_id is not None:
        query = query.where(Project.department_id == department_id)
    if owner_id is not None:
        query = query.where(Project.owner_id == owner_id)
    if mine:
        query = query.where(
            or_(
                Project.owner_id == viewer.id,
                Project.id.in_(
                    select(ProjectMember.project_id).where(ProjectMember.user_id == viewer.id)
                ),
            )
        )
    if research_area_id is not None:
        area_ids = select(ResearchArea.id).where(
            or_(ResearchArea.id == research_area_id, ResearchArea.parent_id == research_area_id)
        )
        query = query.where(
            Project.id.in_(
                select(ProjectResearchArea.project_id).where(
                    ProjectResearchArea.research_area_id.in_(area_ids)
                )
            )
        )
    if skill_id is not None:
        query = query.where(
            Project.id.in_(select(ProjectSkill.project_id).where(ProjectSkill.skill_id == skill_id))
        )

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    if q:
        tsquery = func.websearch_to_tsquery("english", q)
        query = query.order_by(func.ts_rank(Project.search_document, tsquery).desc())
    query = query.order_by(Project.created_at.desc())
    projects = db.execute(query.offset(params.offset).limit(params.page_size)).scalars().all()
    return Page[ProjectCard](
        items=_to_cards(db, projects), page=params.page, page_size=params.page_size, total=total
    )


def review_queue(db: Session, reviewer: User) -> list[ProjectCard]:
    query = select(Project).where(
        Project.deleted_at.is_(None), Project.status == ProjectStatus.PENDING_REVIEW
    )
    if reviewer.role is not UserRole.ADMIN:
        if (
            reviewer.coordinator_scope_type is not CoordinatorScopeType.DEPARTMENT
            or reviewer.coordinator_scope_id is None
        ):
            return []
        query = query.where(Project.department_id == reviewer.coordinator_scope_id)
    projects = db.execute(query.order_by(Project.updated_at)).scalars().all()
    return _to_cards(db, projects)


# --- writes ----------------------------------------------------------------


def create_project(db: Session, owner: User, data: ProjectCreate) -> ProjectRead:
    _validate_tags(db, data.skill_ids, data.research_area_ids)
    project = Project(
        title=data.title,
        summary=data.summary,
        description=data.description,
        objectives=data.objectives,
        start_date=data.start_date,
        end_date=data.end_date,
        owner_id=owner.id,
        department_id=owner.department_id,
        status=ProjectStatus.DRAFT,
    )
    db.add(project)
    db.flush()
    _replace_tags(db, project.id, data.skill_ids, data.research_area_ids)
    db.commit()
    db.refresh(project)
    return _to_read(db, project)


def update_project(
    db: Session, actor: User, project_id: uuid.UUID, data: ProjectUpdate
) -> ProjectRead:
    project = _load_visible(db, actor, project_id)
    assert_owner(actor, project)
    if project.status not in EDITABLE_STATUSES:
        raise InvalidTransitionError

    _validate_tags(db, data.skill_ids or [], data.research_area_ids or [])
    for field in ("title", "summary", "description"):
        value = getattr(data, field)
        if value is not None:
            setattr(project, field, value)
    fields_set = data.model_fields_set
    for field in ("objectives", "start_date", "end_date"):
        if field in fields_set:
            setattr(project, field, getattr(data, field))
    if project.start_date and project.end_date and project.start_date > project.end_date:
        raise InvalidDateRangeError

    _replace_tags(db, project.id, data.skill_ids, data.research_area_ids)
    db.commit()
    db.refresh(project)
    return _to_read(db, project)


def _change_status(project: Project, target: ProjectStatus, actor: Actor) -> None:
    assert_transition(project.status, target, actor)
    project.status = target


def submit_project(db: Session, actor: User, project_id: uuid.UUID) -> ProjectRead:
    project = _load_visible(db, actor, project_id)
    assert_owner(actor, project)
    profile = db.get(ResearcherProfile, actor.id)
    if profile is None or profile.verification_status is not VerificationStatus.VERIFIED:
        raise OwnerNotVerifiedError
    _change_status(project, ProjectStatus.PENDING_REVIEW, "owner")
    db.commit()
    db.refresh(project)
    return _to_read(db, project)


def review_project(
    db: Session, reviewer: User, project_id: uuid.UUID, data: ReviewRequest, *, ip: str | None
) -> ProjectRead:
    # Visibility doubles as the coordinator's department scope check: a
    # pending project outside their department is a 404.
    project = _load_visible(db, reviewer, project_id)
    assert_not_own_project(reviewer, project)
    before = {"status": project.status.value}
    target = ProjectStatus.ACTIVE if data.decision == "approve" else ProjectStatus.DRAFT
    _change_status(project, target, "reviewer")
    project.review_comment = data.comment
    project.reviewed_by = reviewer.id
    project.reviewed_at = datetime.now(UTC)
    db.flush()
    EVENT_BUS.publish(
        db,
        Event(
            name=EventName.PROJECT_REVIEWED,
            actor_id=reviewer.id,
            payload={
                "recipient_id": project.owner_id,
                "project_id": project.id,
                "project_title": project.title,
                "status": target.value,
                "comment": data.comment,
            },
        ),
    )
    audit_service.record(
        db,
        actor_id=reviewer.id,
        action="project.approved" if data.decision == "approve" else "project.rejected",
        entity_type="project",
        entity_id=project.id,
        before=before,
        after={"status": project.status.value, "comment": data.comment},
        ip=ip,
    )
    db.commit()
    db.refresh(project)
    return _to_read(db, project)


def complete_project(db: Session, actor: User, project_id: uuid.UUID) -> ProjectRead:
    project = _load_visible(db, actor, project_id)
    assert_owner(actor, project)
    _change_status(project, ProjectStatus.COMPLETED, "owner")
    db.commit()
    db.refresh(project)
    return _to_read(db, project)


def archive_project(
    db: Session, actor: User, project_id: uuid.UUID, *, ip: str | None
) -> ProjectRead:
    project = _load_visible(db, actor, project_id)
    if actor.role is UserRole.ADMIN and project.owner_id != actor.id:
        before = {"status": project.status.value}
        _change_status(project, ProjectStatus.ARCHIVED, "admin")
        db.flush()
        audit_service.record(
            db,
            actor_id=actor.id,
            action="project.archived",
            entity_type="project",
            entity_id=project.id,
            before=before,
            after={"status": project.status.value},
            ip=ip,
        )
    else:
        assert_owner(actor, project)
        _change_status(project, ProjectStatus.ARCHIVED, "owner")
    db.commit()
    db.refresh(project)
    return _to_read(db, project)


def delete_project(db: Session, actor: User, project_id: uuid.UUID, *, ip: str | None) -> None:
    """A DRAFT is soft-deleted; anything else is archived instead, so an
    approved project's history is never destroyed."""
    project = _load_visible(db, actor, project_id)
    if project.status is ProjectStatus.DRAFT:
        assert_owner(actor, project)
        project.deleted_at = datetime.now(UTC)
        db.commit()
        return
    archive_project(db, actor, project_id, ip=ip)


# --- members ---------------------------------------------------------------


def list_members(db: Session, viewer: User, project_id: uuid.UUID) -> list[MemberRead]:
    project = _load_visible(db, viewer, project_id)
    return _members(db, project.id)


def add_member(
    db: Session, actor: User, project_id: uuid.UUID, data: MemberCreate
) -> list[MemberRead]:
    project = _load_visible(db, actor, project_id)
    assert_owner(actor, project)
    target = db.get(User, data.user_id)
    if target is None or not target.is_active:
        raise MemberNotFoundError
    db.add(ProjectMember(project_id=project.id, user_id=data.user_id, member_role=data.member_role))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateMemberError from exc
    return _members(db, project.id)


def remove_member(db: Session, actor: User, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
    project = _load_visible(db, actor, project_id)
    assert_owner(actor, project)
    member = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == user_id
        )
    ).scalar_one_or_none()
    if member is None:
        raise MemberNotFoundError
    db.delete(member)
    db.commit()
