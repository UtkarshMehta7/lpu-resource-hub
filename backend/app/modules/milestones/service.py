"""Milestone business rules.

Visibility is borrowed wholesale from projects: a milestone is visible exactly
when its project is, so every read starts by loading the project through
`projects.service._load_visible`. That keeps one visibility rule in the
codebase instead of two that drift, and it means a milestone on a project the
caller may not know about is a 404 rather than a 403.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.audit import service as audit
from app.modules.milestones.models import (
    SETTLED_STATUSES,
    Milestone,
    MilestoneDependency,
    MilestoneStatus,
)
from app.modules.milestones.policies import (
    Actor,
    CrossProjectDependencyError,
    DependencyCycleError,
    NotOwnerError,
    ProjectNotEditableError,
    assert_transition,
)
from app.modules.milestones.risk import NEEDS_ATTENTION, Risk, RiskInput, assess, days_until
from app.modules.milestones.schemas import (
    AtRiskMilestone,
    AtRiskProject,
    MilestoneCreate,
    MilestoneLink,
    MilestoneRead,
    MilestoneUpdate,
    MyMilestone,
)
from app.modules.projects.models import Project, ProjectMember
from app.modules.projects.policies import EDITABLE_STATUSES, visibility_filter
from app.modules.projects.service import ProjectNotFoundError, _load_visible
from app.modules.users.models import User

MAX_MILESTONES_PER_PROJECT = 200


class MilestoneNotFoundError(Exception):
    """No such milestone, or its project is not visible to the caller."""


class TooManyMilestonesError(Exception):
    """The project already has as many milestones as it may have."""


# --- loading ---------------------------------------------------------------


def _today() -> date:
    return datetime.now(UTC).date()


def _threshold() -> int:
    return get_settings().milestone_at_risk_days


def _load(db: Session, viewer: User, milestone_id: uuid.UUID) -> tuple[Milestone, Project]:
    """A milestone and its project, or 404 if either is out of reach."""
    milestone = db.get(Milestone, milestone_id)
    if milestone is None:
        raise MilestoneNotFoundError
    try:
        project = _load_visible(db, viewer, milestone.project_id)
    except ProjectNotFoundError as exc:
        # Not "forbidden": the caller must not learn the milestone exists.
        raise MilestoneNotFoundError from exc
    return milestone, project


def actor_for(db: Session, user: User, project: Project) -> Actor | None:
    """Which actor the caller is for this project, if either."""
    if project.owner_id == user.id:
        return "owner"
    is_member = db.scalar(
        select(func.count())
        .select_from(ProjectMember)
        .where(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id)
    )
    return "member" if is_member else None


def _assert_owner(db: Session, user: User, project: Project) -> None:
    if actor_for(db, user, project) != "owner":
        raise NotOwnerError


def _assert_project_editable(project: Project) -> None:
    """The plan may only change while the project is drafting or running.

    Reuses the projects module's own constant: a milestone added while a
    project sits in review would change what the reviewer approved.
    """
    if project.status not in EDITABLE_STATUSES:
        raise ProjectNotEditableError


# --- assembling the read shape ---------------------------------------------


def _dependency_map(
    db: Session, milestone_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    if not milestone_ids:
        return {}
    rows = db.execute(
        select(MilestoneDependency.milestone_id, MilestoneDependency.depends_on_id).where(
            MilestoneDependency.milestone_id.in_(milestone_ids)
        )
    ).all()
    edges: dict[uuid.UUID, list[uuid.UUID]] = {}
    for milestone_id, depends_on_id in rows:
        edges.setdefault(milestone_id, []).append(depends_on_id)
    return edges


def _to_reads(db: Session, milestones: Sequence[Milestone]) -> list[MilestoneRead]:
    """Turn rows into responses, deriving risk for the whole set at once."""
    if not milestones:
        return []
    today, threshold = _today(), _threshold()
    by_id = {m.id: m for m in milestones}
    edges = _dependency_map(db, list(by_id))

    # A dependency may point at a milestone outside this set (another page,
    # or one the caller cannot see); fetch what is missing so `blocked` is
    # judged on real data rather than silently downgraded.
    missing = {dep for deps in edges.values() for dep in deps if dep not in by_id}
    extra: dict[uuid.UUID, Milestone] = {}
    if missing:
        extra = {
            m.id: m for m in db.scalars(select(Milestone).where(Milestone.id.in_(missing))).all()
        }

    def as_input(milestone: Milestone) -> RiskInput:
        return RiskInput(status=milestone.status, due_date=milestone.due_date)

    reads: list[MilestoneRead] = []
    for milestone in milestones:
        upstream = [by_id.get(dep) or extra.get(dep) for dep in edges.get(milestone.id, [])]
        resolved = [m for m in upstream if m is not None]
        risk = assess(
            as_input(milestone),
            today=today,
            threshold_days=threshold,
            depends_on=[as_input(m) for m in resolved],
        )
        blocked_by = [
            m
            for m in resolved
            if m.status not in SETTLED_STATUSES
            and assess(as_input(m), today=today, threshold_days=threshold)
            in (Risk.OVERDUE, Risk.AT_RISK)
        ]
        reads.append(
            MilestoneRead(
                **{
                    field: getattr(milestone, field)
                    for field in (
                        "id",
                        "project_id",
                        "title",
                        "description",
                        "due_date",
                        "status",
                        "position",
                        "completed_at",
                        "completed_by",
                        "created_at",
                        "updated_at",
                    )
                },
                risk=risk,
                days_until_due=days_until(milestone.due_date, today),
                depends_on=[MilestoneLink.model_validate(m) for m in resolved],
                blocked_by=[MilestoneLink.model_validate(m) for m in blocked_by],
            )
        )
    return reads


def _ordered(project_id: uuid.UUID) -> Select[tuple[Milestone]]:
    return (
        select(Milestone)
        .where(Milestone.project_id == project_id)
        .order_by(Milestone.position, Milestone.due_date, Milestone.id)
    )


# --- reads -----------------------------------------------------------------


def list_milestones(db: Session, viewer: User, project_id: uuid.UUID) -> list[MilestoneRead]:
    _load_visible(db, viewer, project_id)
    return _to_reads(db, db.scalars(_ordered(project_id)).all())


def get_milestone(db: Session, viewer: User, milestone_id: uuid.UUID) -> MilestoneRead:
    milestone, _ = _load(db, viewer, milestone_id)
    return _to_reads(db, [milestone])[0]


def my_milestones(db: Session, viewer: User, *, limit: int = 50) -> list[MyMilestone]:
    """Outstanding milestones on projects the caller owns or works on.

    Soonest first, and settled ones are left out: this answers "what do I owe
    and when", not "what has this team ever planned".
    """
    rows = db.execute(
        select(Milestone, Project.title)
        .join(Project, Project.id == Milestone.project_id)
        .where(
            Project.deleted_at.is_(None),
            Milestone.status.not_in(tuple(SETTLED_STATUSES)),
            Project.id.in_(
                select(Project.id).where(
                    (Project.owner_id == viewer.id)
                    | Project.id.in_(
                        select(ProjectMember.project_id).where(ProjectMember.user_id == viewer.id)
                    )
                )
            ),
        )
        .order_by(Milestone.due_date, Milestone.id)
        .limit(limit)
    ).all()
    reads = {r.id: r for r in _to_reads(db, [row[0] for row in rows])}
    return [
        MyMilestone(**reads[row[0].id].model_dump(), project_title=row[1])
        for row in rows
        if row[0].id in reads
    ]


def at_risk_projects(db: Session, viewer: User) -> list[AtRiskProject]:
    """Projects with at least one milestone needing attention, worst first.

    Scoped by the same visibility rule as everything else, so a coordinator
    sees their department and an admin sees everything.
    """
    today = _today()
    rows = db.execute(
        select(Milestone, Project, User.full_name, User.registration_number)
        .join(Project, Project.id == Milestone.project_id)
        .join(User, User.id == Project.owner_id)
        .where(
            Project.deleted_at.is_(None),
            Milestone.status.not_in(tuple(SETTLED_STATUSES)),
            visibility_filter(viewer),
        )
        .order_by(Milestone.due_date, Milestone.id)
    ).all()
    if not rows:
        return []

    reads = {r.id: r for r in _to_reads(db, [row[0] for row in rows])}
    grouped: dict[uuid.UUID, AtRiskProject] = {}
    for milestone, project, owner_name, owner_reg in rows:
        read = reads.get(milestone.id)
        if read is None or read.risk not in NEEDS_ATTENTION:
            continue
        entry = grouped.get(project.id)
        if entry is None:
            entry = AtRiskProject(
                project_id=project.id,
                title=project.title,
                owner_id=project.owner_id,
                owner_name=owner_name,
                owner_registration_number=owner_reg,
                department_id=project.department_id,
                overdue_count=0,
                at_risk_count=0,
                blocked_count=0,
                milestones=[],
            )
            grouped[project.id] = entry
        if read.risk is Risk.OVERDUE:
            entry.overdue_count += 1
        elif read.risk is Risk.AT_RISK:
            entry.at_risk_count += 1
        else:
            entry.blocked_count += 1
        entry.milestones.append(
            AtRiskMilestone(
                id=milestone.id,
                title=milestone.title,
                due_date=milestone.due_date,
                status=milestone.status,
                risk=read.risk,
                days_until_due=days_until(milestone.due_date, today),
            )
        )
    # Most overdue first: that is the order somebody triaging would choose.
    return sorted(
        grouped.values(),
        key=lambda p: (-p.overdue_count, -p.blocked_count, -p.at_risk_count, p.title),
    )


# --- writes ----------------------------------------------------------------


def _next_position(db: Session, project_id: uuid.UUID) -> int:
    highest = db.scalar(
        select(func.max(Milestone.position)).where(Milestone.project_id == project_id)
    )
    return (highest or 0) + 1


def _shift_positions_for(db: Session, project_id: uuid.UUID, position: int) -> None:
    """Make room at `position` by pushing everything at or after it down.

    Done as one statement rather than a loop so the unique constraint is never
    transiently violated mid-way.
    """
    db.execute(
        update(Milestone)
        .where(Milestone.project_id == project_id, Milestone.position >= position)
        .values(position=Milestone.position + 1)
    )


def create_milestone(
    db: Session, actor: User, project_id: uuid.UUID, data: MilestoneCreate
) -> MilestoneRead:
    project = _load_visible(db, actor, project_id)
    _assert_owner(db, actor, project)
    _assert_project_editable(project)

    count = db.scalar(
        select(func.count()).select_from(Milestone).where(Milestone.project_id == project_id)
    )
    if (count or 0) >= MAX_MILESTONES_PER_PROJECT:
        raise TooManyMilestonesError

    if data.position is None:
        position = _next_position(db, project_id)
    else:
        position = data.position
        _shift_positions_for(db, project_id, position)

    milestone = Milestone(
        project_id=project_id,
        title=data.title,
        description=data.description,
        due_date=data.due_date,
        position=position,
    )
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    return _to_reads(db, [milestone])[0]


def update_milestone(
    db: Session, actor: User, milestone_id: uuid.UUID, data: MilestoneUpdate
) -> MilestoneRead:
    milestone, project = _load(db, actor, milestone_id)
    _assert_owner(db, actor, project)
    _assert_project_editable(project)

    fields_set = data.model_fields_set
    for field in ("title", "due_date"):
        value = getattr(data, field)
        if value is not None:
            setattr(milestone, field, value)
    if "description" in fields_set:
        milestone.description = data.description
    if data.position is not None and data.position != milestone.position:
        _shift_positions_for(db, project.id, data.position)
        milestone.position = data.position

    db.commit()
    db.refresh(milestone)
    return _to_reads(db, [milestone])[0]


def delete_milestone(
    db: Session, actor: User, milestone_id: uuid.UUID, *, ip: str | None = None
) -> None:
    milestone, project = _load(db, actor, milestone_id)
    _assert_owner(db, actor, project)
    _assert_project_editable(project)
    audit.record(
        db,
        actor_id=actor.id,
        action="milestone.deleted",
        entity_type="milestone",
        entity_id=milestone.id,
        before={"title": milestone.title, "project_id": str(project.id)},
        ip=ip,
    )
    db.delete(milestone)
    db.commit()


def change_status(
    db: Session, actor: User, milestone_id: uuid.UUID, target: MilestoneStatus
) -> MilestoneRead:
    milestone, project = _load(db, actor, milestone_id)
    who = actor_for(db, actor, project)
    if who is None:
        # Visible but not on the team: they may read, never move.
        raise NotOwnerError
    _assert_project_editable(project)
    assert_transition(milestone.status, target, who)

    milestone.status = target
    if target is MilestoneStatus.DONE:
        milestone.completed_at = datetime.now(UTC)
        milestone.completed_by = actor.id
    else:
        # Reopening clears the record of completion; a CHECK constraint keeps
        # "done" and a completion date in step either way.
        milestone.completed_at = None
        milestone.completed_by = None

    db.commit()
    db.refresh(milestone)
    return _to_reads(db, [milestone])[0]


# --- dependencies ----------------------------------------------------------


def _reaches(db: Session, start: uuid.UUID, target: uuid.UUID) -> bool:
    """Whether `start` already waits on `target`, directly or through others.

    A plain breadth-first walk over the edge table. The alternative is a
    recursive CTE, which is harder to read for graphs this small -- a project
    is capped at 200 milestones -- and no faster in practice.
    """
    seen: set[uuid.UUID] = set()
    frontier = [start]
    while frontier:
        current = frontier.pop()
        if current == target:
            return True
        if current in seen:
            continue
        seen.add(current)
        frontier.extend(
            db.scalars(
                select(MilestoneDependency.depends_on_id).where(
                    MilestoneDependency.milestone_id == current
                )
            ).all()
        )
    return False


def add_dependency(
    db: Session, actor: User, milestone_id: uuid.UUID, depends_on_id: uuid.UUID
) -> MilestoneRead:
    milestone, project = _load(db, actor, milestone_id)
    _assert_owner(db, actor, project)
    _assert_project_editable(project)

    upstream = db.get(Milestone, depends_on_id)
    if upstream is None:
        raise MilestoneNotFoundError
    if upstream.project_id != milestone.project_id:
        raise CrossProjectDependencyError
    if upstream.id == milestone.id:
        # Also refused by a CHECK; caught here for a clearer message.
        raise DependencyCycleError
    # Adding A -> B is a cycle exactly when B already reaches A.
    if _reaches(db, depends_on_id, milestone_id):
        raise DependencyCycleError

    existing = db.get(MilestoneDependency, (milestone_id, depends_on_id))
    if existing is None:
        db.add(MilestoneDependency(milestone_id=milestone_id, depends_on_id=depends_on_id))
        db.commit()
    db.refresh(milestone)
    return _to_reads(db, [milestone])[0]


def remove_dependency(
    db: Session, actor: User, milestone_id: uuid.UUID, depends_on_id: uuid.UUID
) -> MilestoneRead:
    milestone, project = _load(db, actor, milestone_id)
    _assert_owner(db, actor, project)
    _assert_project_editable(project)
    edge = db.get(MilestoneDependency, (milestone_id, depends_on_id))
    if edge is not None:
        db.delete(edge)
        db.commit()
    db.refresh(milestone)
    return _to_reads(db, [milestone])[0]


__all__ = [
    "MAX_MILESTONES_PER_PROJECT",
    "MilestoneNotFoundError",
    "TooManyMilestonesError",
    "actor_for",
    "add_dependency",
    "at_risk_projects",
    "change_status",
    "create_milestone",
    "delete_milestone",
    "get_milestone",
    "list_milestones",
    "my_milestones",
    "remove_dependency",
    "update_milestone",
]
