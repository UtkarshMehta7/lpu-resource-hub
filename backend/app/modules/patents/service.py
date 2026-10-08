"""Patents: CRUD, the office lifecycle, the institution's approval, listing.

Patents are readable by every signed-in user, like publications -- they are
either published by an office or on their way to being. What is *not* public
is the projects they link to: a linked project is only shown to viewers who
may see it, so linking a patent to a draft cannot leak the draft's title.

Services never import FastAPI.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams
from app.core.permissions import ROLE_PERMISSIONS, Permission
from app.modules.audit import service as audit_service
from app.modules.patents.models import Patent, PatentInventor, PatentStatus, ProjectPatent
from app.modules.patents.policies import (
    BEFORE_THE_OFFICE,
    DATE_REQUIRED,
    NOTE_REQUIRED,
    NUMBER_FIELD,
    assert_may_move,
    initial_verification,
    next_statuses,
)
from app.modules.patents.schemas import (
    InventorInput,
    InventorRead,
    LinkedProject,
    PatentCreate,
    PatentDecision,
    PatentRead,
    PatentTransition,
    PatentUpdate,
)
from app.modules.profiles.models import VerificationStatus
from app.modules.projects.models import Project, ProjectMember
from app.modules.projects.policies import visibility_filter
from app.modules.users.models import User, UserRole


class PatentNotFoundError(Exception):
    """No patent with this id."""


class NotCreatorError(Exception):
    """Only the creator (or an admin, for deletion) may change a patent."""


class DuplicateNumberError(Exception):
    """Another patent in this jurisdiction already carries that number."""


class UnknownInventorError(Exception):
    """An inventor's user_id doesn't name an active user."""


class ProjectLinkError(Exception):
    """A linked project doesn't exist, or the creator neither owns nor belongs to it."""


class MissingTransitionDateError(Exception):
    """That status cannot be entered without the date the office issued."""


class MissingDecisionNoteError(Exception):
    """Declining without a reason is what stops the next person disclosing."""


class OutOfScopeError(Exception):
    """A coordinator may only decide records from their own department."""


class AlreadyDecidedError(Exception):
    """This record has already been verified or rejected."""


# --- validation --------------------------------------------------------------


def _validate_inventors(db: Session, inventors: Sequence[InventorInput]) -> None:
    user_ids = {i.user_id for i in inventors if i.user_id is not None}
    if not user_ids:
        return
    found = set(
        db.execute(select(User.id).where(User.id.in_(user_ids), User.is_active.is_(True))).scalars()
    )
    if user_ids - found:
        raise UnknownInventorError


def _validate_project_links(db: Session, actor: User, project_ids: Sequence[uuid.UUID]) -> None:
    if not project_ids:
        return
    linkable = set(
        db.execute(
            select(Project.id).where(
                Project.id.in_(project_ids),
                Project.deleted_at.is_(None),
                or_(
                    Project.owner_id == actor.id,
                    Project.id.in_(
                        select(ProjectMember.project_id).where(ProjectMember.user_id == actor.id)
                    ),
                ),
            )
        ).scalars()
    )
    if set(project_ids) - linkable:
        raise ProjectLinkError


def _replace_inventors(
    db: Session, patent_id: uuid.UUID, inventors: Sequence[InventorInput]
) -> None:
    db.execute(delete(PatentInventor).where(PatentInventor.patent_id == patent_id))
    db.flush()
    db.add_all(
        PatentInventor(
            patent_id=patent_id,
            user_id=inventor.user_id,
            external_name=inventor.external_name,
            inventor_order=position,
        )
        for position, inventor in enumerate(inventors, start=1)
    )


def _replace_links(db: Session, patent_id: uuid.UUID, project_ids: Sequence[uuid.UUID]) -> None:
    db.execute(delete(ProjectPatent).where(ProjectPatent.patent_id == patent_id))
    db.add_all(ProjectPatent(project_id=pid, patent_id=patent_id) for pid in set(project_ids))


def _commit_or_duplicate(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "number" in str(exc.orig).lower():
            raise DuplicateNumberError from exc
        raise


def _may_review(actor: User) -> bool:
    return Permission.PATENT_VERIFY in ROLE_PERMISSIONS[actor.role]


def _allocate_reference(db: Session, when: date) -> str:
    """The IP cell's docket: LPU/IDF/2026/0007.

    Human-quotable on purpose -- an inventor chasing their disclosure says
    this down a phone, and nobody reads a UUID aloud. Allocated per calendar
    year from the highest already issued, so a deleted record leaves a gap
    rather than letting the next one reuse its number; a reference that has
    ever been quoted must never point at a different invention.

    A unique index is the real guard: two disclosures in the same second get
    the same count, and the loser retries.
    """
    prefix = f"LPU/IDF/{when.year}/"
    highest = db.execute(
        select(func.max(Patent.reference)).where(Patent.reference.like(f"{prefix}%"))
    ).scalar_one_or_none()
    nxt = int(highest.rsplit("/", 1)[1]) + 1 if highest else 1
    return f"{prefix}{nxt:04d}"


# --- building responses ------------------------------------------------------


def _inventors(db: Session, patent_id: uuid.UUID) -> list[InventorRead]:
    rows = db.execute(
        select(PatentInventor, User.full_name, User.registration_number)
        .outerjoin(User, User.id == PatentInventor.user_id)
        .where(PatentInventor.patent_id == patent_id)
        .order_by(PatentInventor.inventor_order)
    ).all()
    return [
        InventorRead(
            user_id=inventor.user_id,
            name=full_name if inventor.user_id is not None else (inventor.external_name or ""),
            registration_number=registration_number,
            inventor_order=inventor.inventor_order,
        )
        for inventor, full_name, registration_number in rows
    ]


def _visible_projects(db: Session, viewer: User, patent_id: uuid.UUID) -> list[LinkedProject]:
    rows = db.execute(
        select(Project.id, Project.title)
        .join(ProjectPatent, ProjectPatent.project_id == Project.id)
        .where(
            ProjectPatent.patent_id == patent_id,
            Project.deleted_at.is_(None),
            visibility_filter(viewer),
        )
        .order_by(Project.title)
    ).all()
    return [LinkedProject(id=pid, title=title) for pid, title in rows]


def _to_read(db: Session, viewer: User, patent: Patent) -> PatentRead:
    wanted = [
        i for i in (patent.created_by, patent.verified_by, patent.assessed_by) if i is not None
    ]
    names: dict[uuid.UUID, str] = {
        user_id: full_name
        for user_id, full_name in db.execute(
            select(User.id, User.full_name).where(User.id.in_(wanted))
        ).all()
    }
    return PatentRead(
        id=patent.id,
        title=patent.title,
        abstract=patent.abstract,
        jurisdiction=patent.jurisdiction,
        application_number=patent.application_number,
        publication_number=patent.publication_number,
        grant_number=patent.grant_number,
        filing_date=patent.filing_date,
        publication_date=patent.publication_date,
        grant_date=patent.grant_date,
        status=patent.status,
        assignee=patent.assignee,
        url=patent.url,
        created_by=patent.created_by,
        creator_name=names.get(patent.created_by, ""),
        reference=patent.reference,
        problem_statement=patent.problem_statement,
        novelty=patent.novelty,
        known_prior_art=patent.known_prior_art,
        public_disclosure_date=patent.public_disclosure_date,
        public_disclosure_note=patent.public_disclosure_note,
        funding_source=patent.funding_source,
        commercial_potential=patent.commercial_potential,
        assessment_note=patent.assessment_note,
        assessed_by=patent.assessed_by,
        assessed_by_name=names.get(patent.assessed_by) if patent.assessed_by else None,
        assessed_at=patent.assessed_at,
        verification_status=patent.verification_status,
        verified_by=patent.verified_by,
        verified_by_name=names.get(patent.verified_by) if patent.verified_by else None,
        verified_at=patent.verified_at,
        verification_note=patent.verification_note,
        inventors=_inventors(db, patent.id),
        projects=_visible_projects(db, viewer, patent.id),
        next_statuses=next_statuses(
            patent.status,
            is_creator=patent.created_by == viewer.id,
            reviewer=_may_review(viewer),
        ),
        created_at=patent.created_at,
    )


def _load(db: Session, patent_id: uuid.UUID) -> Patent:
    patent = db.get(Patent, patent_id)
    if patent is None:
        raise PatentNotFoundError
    return patent


# --- operations --------------------------------------------------------------


def create_patent(db: Session, creator: User, data: PatentCreate) -> PatentRead:
    """Two ways in, one record.

    An invention being put to the university starts at DISCLOSED and gets a
    docket; a patent already filed elsewhere is recorded as FILED. Everything
    after that goes through the transition table, so no caller can ever place
    a record at an arbitrary stage.
    """
    _validate_inventors(db, data.inventors)
    _validate_project_links(db, creator, data.project_ids)
    status = PatentStatus.FILED if data.already_filed else PatentStatus.DISCLOSED
    patent = Patent(
        title=data.title,
        abstract=data.abstract,
        jurisdiction=data.jurisdiction,
        application_number=data.application_number,
        filing_date=data.filing_date,
        status=status,
        assignee=data.assignee,
        url=data.url,
        created_by=creator.id,
        verification_status=initial_verification(creator),
        problem_statement=data.problem_statement,
        novelty=data.novelty,
        known_prior_art=data.known_prior_art,
        public_disclosure_date=data.public_disclosure_date,
        public_disclosure_note=data.public_disclosure_note,
        funding_source=data.funding_source,
        commercial_potential=data.commercial_potential,
    )
    if patent.verification_status is VerificationStatus.VERIFIED:
        patent.verified_by = creator.id
        patent.verified_at = datetime.now(UTC)
    # A docket belongs to work the university is being asked to file. A patent
    # recorded as already filed somewhere else never entered that queue.
    if status is PatentStatus.DISCLOSED:
        patent.reference = _allocate_reference(db, date.today())
    db.add(patent)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateNumberError from exc
    _replace_inventors(db, patent.id, data.inventors)
    _replace_links(db, patent.id, data.project_ids)
    _commit_or_duplicate(db)
    db.refresh(patent)
    return _to_read(db, creator, patent)


def get_patent(db: Session, viewer: User, patent_id: uuid.UUID) -> PatentRead:
    return _to_read(db, viewer, _load(db, patent_id))


def update_patent(db: Session, actor: User, patent_id: uuid.UUID, data: PatentUpdate) -> PatentRead:
    patent = _load(db, patent_id)
    if patent.created_by != actor.id:
        raise NotCreatorError

    if data.inventors is not None:
        _validate_inventors(db, data.inventors)
    if data.project_ids is not None:
        _validate_project_links(db, actor, data.project_ids)

    if data.title is not None:
        patent.title = data.title
    # filing_date is NOT editable here: it moves only through the transition
    # that records the filing, so a record cannot claim a priority date the
    # office never gave it.
    for field in (
        "abstract",
        "assignee",
        "application_number",
        "url",
        "problem_statement",
        "novelty",
        "known_prior_art",
        "public_disclosure_date",
        "public_disclosure_note",
        "funding_source",
        "commercial_potential",
    ):
        if field in data.model_fields_set:
            setattr(patent, field, getattr(data, field))

    # Editing the substance withdraws the institution's approval: a verified
    # record is a statement about the content somebody checked, and the
    # content has just changed. The same rule as a profile import sending a
    # verified profile back to PENDING.
    if patent.verification_status is VerificationStatus.VERIFIED:
        patent.verification_status = VerificationStatus.PENDING
        patent.verified_by = None
        patent.verified_at = None

    if data.inventors is not None:
        _replace_inventors(db, patent.id, data.inventors)
    if data.project_ids is not None:
        _replace_links(db, patent.id, data.project_ids)
    _commit_or_duplicate(db)
    db.refresh(patent)
    return _to_read(db, actor, patent)


def move_status(
    db: Session, actor: User, patent_id: uuid.UUID, data: PatentTransition
) -> PatentRead:
    """Move the invention along, if this person is entitled to that move."""
    patent = _load(db, patent_id)
    assert_may_move(
        patent.status,
        data.status,
        is_creator=patent.created_by == actor.id,
        reviewer=_may_review(actor),
    )

    date_field = DATE_REQUIRED.get(data.status)
    if date_field is not None and data.on is None and getattr(patent, date_field) is None:
        raise MissingTransitionDateError
    if data.status in NOTE_REQUIRED and not (data.note or "").strip():
        raise MissingDecisionNoteError

    if date_field is not None and data.on is not None:
        setattr(patent, date_field, data.on)
    number_field = NUMBER_FIELD.get(data.status)
    if number_field is not None and data.number is not None:
        setattr(patent, number_field, data.number)

    # The IP cell's reasoning, recorded against whoever gave it. Kept apart
    # from verification_note, which answers a different question entirely:
    # "are these numbers right", not "should we file this".
    if data.status in BEFORE_THE_OFFICE and _may_review(actor):
        if data.note is not None:
            patent.assessment_note = data.note
        patent.assessed_by = actor.id
        patent.assessed_at = datetime.now(UTC)

    patent.status = data.status
    _commit_or_duplicate(db)
    db.refresh(patent)
    return _to_read(db, actor, patent)


def _in_scope(actor: User, creator_department_id: uuid.UUID | None) -> bool:
    if actor.role is UserRole.ADMIN:
        return True
    return creator_department_id is not None and creator_department_id == actor.department_id


def decide(
    db: Session, actor: User, patent_id: uuid.UUID, data: PatentDecision, *, ip: str | None
) -> PatentRead:
    """Approve or reject the RECORD -- not the invention, and not the grant."""
    patent = _load(db, patent_id)
    if patent.verification_status is not VerificationStatus.PENDING:
        raise AlreadyDecidedError
    creator_department = db.execute(
        select(User.department_id).where(User.id == patent.created_by)
    ).scalar_one_or_none()
    if not _in_scope(actor, creator_department):
        raise OutOfScopeError

    patent.verification_status = (
        VerificationStatus.VERIFIED if data.decision else VerificationStatus.REJECTED
    )
    patent.verified_by = actor.id
    patent.verified_at = datetime.now(UTC)
    patent.verification_note = data.note
    audit_service.record(
        db,
        actor_id=actor.id,
        action="patent.verified" if data.decision else "patent.rejected",
        entity_type="patent",
        entity_id=patent.id,
        before={"verification_status": VerificationStatus.PENDING.value},
        after={"verification_status": patent.verification_status.value, "note": data.note},
        ip=ip,
    )
    db.commit()
    db.refresh(patent)
    return _to_read(db, actor, patent)


def delete_patent(db: Session, actor: User, patent_id: uuid.UUID, *, ip: str | None) -> None:
    patent = _load(db, patent_id)
    is_creator = patent.created_by == actor.id
    if not is_creator and actor.role is not UserRole.ADMIN:
        raise NotCreatorError
    if not is_creator:
        audit_service.record(
            db,
            actor_id=actor.id,
            action="patent.deleted",
            entity_type="patent",
            entity_id=patent.id,
            before={"title": patent.title, "created_by": str(patent.created_by)},
            after=None,
            ip=ip,
        )
    db.delete(patent)
    db.commit()


# --- listing -----------------------------------------------------------------


def _filtered(
    *,
    q: str | None,
    inventor_id: uuid.UUID | None,
    status: PatentStatus | None,
    verification_status: VerificationStatus | None,
    jurisdiction: str | None,
) -> Select[tuple[Patent]]:
    query = select(Patent)
    if q:
        query = query.where(
            Patent.search_document.op("@@")(func.websearch_to_tsquery("english", q))
        )
    if inventor_id is not None:
        query = query.where(
            or_(
                Patent.created_by == inventor_id,
                Patent.id.in_(
                    select(PatentInventor.patent_id).where(PatentInventor.user_id == inventor_id)
                ),
            )
        )
    if status is not None:
        query = query.where(Patent.status == status)
    if verification_status is not None:
        query = query.where(Patent.verification_status == verification_status)
    if jurisdiction is not None:
        query = query.where(Patent.jurisdiction == jurisdiction.upper())
    return query


def list_patents(
    db: Session,
    viewer: User,
    params: PageParams,
    *,
    q: str | None = None,
    inventor_id: uuid.UUID | None = None,
    status: PatentStatus | None = None,
    verification_status: VerificationStatus | None = None,
    jurisdiction: str | None = None,
) -> Page[PatentRead]:
    query = _filtered(
        q=q,
        inventor_id=inventor_id,
        status=status,
        verification_status=verification_status,
        jurisdiction=jurisdiction,
    )
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    if q:
        tsquery = func.websearch_to_tsquery("english", q)
        query = query.order_by(func.ts_rank(Patent.search_document, tsquery).desc())
    query = query.order_by(Patent.filing_date.desc(), Patent.title)
    rows = db.execute(query.offset(params.offset).limit(params.page_size)).scalars().all()
    return Page[PatentRead](
        items=[_to_read(db, viewer, patent) for patent in rows],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )


def review_queue(db: Session, actor: User) -> list[PatentRead]:
    """What is waiting on this person, and only what they could act on.

    Two kinds, deliberately in one queue: disclosures the IP cell has not
    assessed, and records whose numbers nobody has checked. Both are "this
    needs you", and splitting them into two pages would have meant two places
    to forget to look.

    Filtered through the same scope rule the decision enforces, or it is a
    dead button -- the mistake the project review queue was written to avoid.
    """
    waiting = or_(
        Patent.status.in_([PatentStatus.DISCLOSED, PatentStatus.UNDER_ASSESSMENT]),
        Patent.verification_status == VerificationStatus.PENDING,
    )
    query = select(Patent).join(User, User.id == Patent.created_by).where(waiting)
    if actor.role is not UserRole.ADMIN:
        query = query.where(User.department_id == actor.department_id)
    rows = db.execute(query.order_by(Patent.created_at)).scalars().all()
    return [_to_read(db, actor, patent) for patent in rows]
