"""The duplicate review queue. Services never import FastAPI."""

from __future__ import annotations

import uuid
from collections.abc import Collection
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.core.pagination import Page, PageParams
from app.modules.audit import service as audit_service
from app.modules.deduplication import detect
from app.modules.deduplication.models import DuplicateStatus, PublicationDuplicate
from app.modules.deduplication.policies import assert_transition
from app.modules.deduplication.schemas import (
    DuplicateDecision,
    DuplicateRead,
    PublicationSide,
    ScanResult,
)
from app.modules.publications.models import (
    ProjectPublication,
    Publication,
    PublicationAuthor,
    PublicationType,
)
from app.modules.users.models import User


class DuplicateNotFoundError(Exception):
    """No such review row."""


class KeepIdRequiredError(Exception):
    """A merge has to say which record survives."""


class KeepIdNotInPairError(Exception):
    """The record to keep is not one of the two under review."""


class PairIncompleteError(Exception):
    """One side is already gone, so there is nothing left to merge."""


class NothingToUndoError(Exception):
    """Only a merge with its snapshot intact can be undone."""


# --- scanning ---------------------------------------------------------------


def _records(db: Session, only: Collection[uuid.UUID] | None = None) -> list[detect.Record]:
    """The little each publication needs to expose to be compared.

    `only` restricts the load to the shortlist the database produced, so a
    scan reads the rows it will actually score rather than the whole register.
    """
    if only is not None and not only:
        return []
    authors: dict[uuid.UUID, set[str]] = {}
    author_query = (
        select(PublicationAuthor.publication_id, PublicationAuthor.external_name, User.full_name)
        .outerjoin(User, User.id == PublicationAuthor.user_id)
        .order_by(PublicationAuthor.author_order)
    )
    if only is not None:
        author_query = author_query.where(PublicationAuthor.publication_id.in_(only))
    rows = db.execute(author_query).all()
    for publication_id, external_name, full_name in rows:
        name = (full_name or external_name or "").strip().casefold()
        if name:
            authors.setdefault(publication_id, set()).add(name)

    return [
        detect.Record(
            id=publication.id,
            title=publication.title,
            doi=publication.doi,
            year=publication.year,
            venue=publication.venue,
            author_names=frozenset(authors.get(publication.id, set())),
        )
        for publication in db.execute(
            select(Publication).where(Publication.id.in_(only))
            if only is not None
            else select(Publication)
        ).scalars()
    ]


#: An upper bound on the pairs one scan will consider, so a register that has
#: grown unexpectedly cannot turn a button into a long transaction. The
#: trigram shortlist is already narrow; this is the guard behind it.
PAIR_LIMIT: int = 5000


def _candidate_pairs(db: Session) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Pairs the database thinks are worth scoring.

    Postgres generates the candidates using the trigram index on
    `publications.title` (`ix_publications_title_trgm`, migration 0022), and
    rapidfuzz then scores only what comes back. That division is what the
    brief asks for and what the import path has always done; the review
    queue compared everything with everything in Python until this.

    `a.id < b.id` yields each pair once and in the order the unique
    constraint expects, so the same pair cannot arrive twice in one scan.
    """
    left = aliased(Publication, name="a")
    right = aliased(Publication, name="b")
    rows = db.execute(
        select(left.id, right.id)
        .join(right, left.id < right.id)
        .where(left.title.op("%")(right.title))
        .limit(PAIR_LIMIT)
    ).all()
    return [(a, b) for a, b in rows]


def scan(db: Session, actor: User, *, ip: str | None = None) -> ScanResult:
    """Look for suspected duplicates and put the new ones on the queue.

    Idempotent, and deliberately does not resurrect a decided pair: a
    reviewer's "these are different works" must not reappear next week as
    though nobody had looked. The unique constraint on the ordered pair is
    what makes that true in the database rather than in this function.
    """
    pairs = _candidate_pairs(db)
    wanted = {publication_id for pair in pairs for publication_id in pair}
    records = {record.id: record for record in _records(db, wanted)}
    candidates = detect.score_pairs(
        (records[a], records[b]) for a, b in pairs if a in records and b in records
    )

    known: dict[tuple[uuid.UUID, uuid.UUID], PublicationDuplicate] = {
        (row.publication_a_id, row.publication_b_id): row
        for row in db.execute(select(PublicationDuplicate)).scalars()
        if row.publication_a_id is not None and row.publication_b_id is not None
    }

    new_rows = 0
    already_decided = 0
    for candidate in candidates:
        key = (candidate.publication_a_id, candidate.publication_b_id)
        existing = known.get(key)
        if existing is not None:
            if existing.status is DuplicateStatus.SUSPECTED:
                # Refresh the score and evidence: a record may have been
                # edited since the last scan.
                existing.score = candidate.score
                existing.evidence = candidate.evidence
            else:
                already_decided += 1
            continue
        db.add(
            PublicationDuplicate(
                publication_a_id=candidate.publication_a_id,
                publication_b_id=candidate.publication_b_id,
                score=candidate.score,
                evidence=candidate.evidence,
                status=DuplicateStatus.SUSPECTED,
            )
        )
        new_rows += 1

    examined = int(db.execute(select(func.count()).select_from(Publication)).scalar_one())
    audit_service.record(
        db,
        actor_id=actor.id,
        action="publication.duplicate_scan",
        entity_type="publication_duplicate",
        entity_id=actor.id,
        after={
            "examined": examined,
            "shortlisted_pairs": len(pairs),
            "pairs_found": len(candidates),
            "pairs_new": new_rows,
        },
        ip=ip,
    )
    db.commit()
    return ScanResult(
        examined=examined,
        pairs_found=len(candidates),
        pairs_new=new_rows,
        pairs_already_decided=already_decided,
    )


# --- reading ----------------------------------------------------------------


def _side(db: Session, publication_id: uuid.UUID | None) -> PublicationSide | None:
    if publication_id is None:
        return None
    publication = db.get(Publication, publication_id)
    if publication is None:
        return None
    names = [
        (full_name or external_name or "")
        for external_name, full_name in db.execute(
            select(PublicationAuthor.external_name, User.full_name)
            .outerjoin(User, User.id == PublicationAuthor.user_id)
            .where(PublicationAuthor.publication_id == publication_id)
            .order_by(PublicationAuthor.author_order)
        ).all()
    ]
    projects = db.execute(
        select(func.count())
        .select_from(ProjectPublication)
        .where(ProjectPublication.publication_id == publication_id)
    ).scalar_one()
    return PublicationSide(
        id=publication.id,
        title=publication.title,
        doi=publication.doi,
        url=publication.url,
        venue=publication.venue,
        year=publication.year,
        pub_type=publication.pub_type.value,
        authors=[name for name in names if name],
        project_count=int(projects),
        created_at=publication.created_at,
    )


def _read(db: Session, row: PublicationDuplicate) -> DuplicateRead:
    decider = db.get(User, row.decided_by) if row.decided_by else None
    return DuplicateRead(
        id=row.id,
        status=row.status,
        score=row.score,
        evidence=row.evidence,
        publication_a=_side(db, row.publication_a_id),
        publication_b=_side(db, row.publication_b_id),
        merged_into_id=row.merged_into_id,
        can_undo=row.status is DuplicateStatus.MERGED and row.snapshot is not None,
        decided_by=row.decided_by,
        decided_by_name=decider.full_name if decider else None,
        decided_at=row.decided_at,
        decision_note=row.decision_note,
        created_at=row.created_at,
    )


def list_duplicates(
    db: Session, params: PageParams, *, status: DuplicateStatus | None = None
) -> Page[DuplicateRead]:
    query = select(PublicationDuplicate)
    if status is not None:
        query = query.where(PublicationDuplicate.status == status)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = (
        db.execute(
            query.order_by(
                PublicationDuplicate.score.desc(), PublicationDuplicate.created_at.desc()
            )
            .offset(params.offset)
            .limit(params.page_size)
        )
        .scalars()
        .all()
    )
    return Page[DuplicateRead](
        items=[_read(db, row) for row in rows],
        page=params.page,
        page_size=params.page_size,
        total=int(total),
    )


def get_duplicate(db: Session, duplicate_id: uuid.UUID) -> DuplicateRead:
    row = db.get(PublicationDuplicate, duplicate_id)
    if row is None:
        raise DuplicateNotFoundError
    return _read(db, row)


# --- deciding ---------------------------------------------------------------


def _snapshot(db: Session, publication: Publication) -> dict[str, Any]:
    """Everything needed to put this record back exactly as it was."""
    authors = [
        {
            "user_id": str(author.user_id) if author.user_id else None,
            "external_name": author.external_name,
            "author_order": author.author_order,
        }
        for author in db.execute(
            select(PublicationAuthor)
            .where(PublicationAuthor.publication_id == publication.id)
            .order_by(PublicationAuthor.author_order)
        ).scalars()
    ]
    projects = [
        str(project_id)
        for project_id in db.execute(
            select(ProjectPublication.project_id).where(
                ProjectPublication.publication_id == publication.id
            )
        ).scalars()
    ]
    return {
        "id": str(publication.id),
        "title": publication.title,
        "abstract": publication.abstract,
        "venue": publication.venue,
        "year": publication.year,
        "doi": publication.doi,
        "url": publication.url,
        "pub_type": publication.pub_type.value,
        "created_by": str(publication.created_by),
        "authors": authors,
        "projects": projects,
    }


def _carry_over(db: Session, loser: Publication, winner: Publication) -> dict[str, int]:
    """Move what the losing record holds onto the surviving one.

    Author slots are numbered per publication and unique on
    (publication_id, author_order), so they are appended after the winner's
    last slot rather than moved at their old numbers. An author already on
    the winner is not added twice.
    """
    existing_people = {
        (author.user_id, (author.external_name or "").casefold())
        for author in db.execute(
            select(PublicationAuthor).where(PublicationAuthor.publication_id == winner.id)
        ).scalars()
    }
    next_order = int(
        db.execute(
            select(func.coalesce(func.max(PublicationAuthor.author_order), 0)).where(
                PublicationAuthor.publication_id == winner.id
            )
        ).scalar_one()
    )

    authors_moved = 0
    for author in db.execute(
        select(PublicationAuthor)
        .where(PublicationAuthor.publication_id == loser.id)
        .order_by(PublicationAuthor.author_order)
    ).scalars():
        identity = (author.user_id, (author.external_name or "").casefold())
        if identity in existing_people:
            continue
        next_order += 1
        db.add(
            PublicationAuthor(
                publication_id=winner.id,
                user_id=author.user_id,
                external_name=author.external_name,
                author_order=next_order,
            )
        )
        existing_people.add(identity)
        authors_moved += 1

    linked = {
        project_id
        for project_id in db.execute(
            select(ProjectPublication.project_id).where(
                ProjectPublication.publication_id == winner.id
            )
        ).scalars()
    }
    projects_moved = 0
    for project_id in db.execute(
        select(ProjectPublication.project_id).where(ProjectPublication.publication_id == loser.id)
    ).scalars():
        if project_id in linked:
            continue
        db.add(ProjectPublication(project_id=project_id, publication_id=winner.id))
        projects_moved += 1

    # A DOI the survivor lacks is worth keeping: it is the strongest
    # identifier either record has, and the column is unique, so it can only
    # be taken once the loser is gone.
    return {"authors_moved": authors_moved, "projects_moved": projects_moved}


def decide(
    db: Session,
    actor: User,
    duplicate_id: uuid.UUID,
    decision: DuplicateDecision,
    *,
    ip: str | None = None,
) -> DuplicateRead:
    row = db.get(PublicationDuplicate, duplicate_id)
    if row is None:
        raise DuplicateNotFoundError

    target = {
        "merge": DuplicateStatus.MERGED,
        "separate": DuplicateStatus.SEPARATE,
        "ignore": DuplicateStatus.IGNORED,
    }[decision.action]
    assert_transition(row.status, target)

    detail: dict[str, Any] = {}
    if target is DuplicateStatus.MERGED:
        detail = _merge(db, row, decision)

    row.status = target
    row.decided_by = actor.id
    row.decided_at = datetime.now(UTC)
    row.decision_note = decision.note
    audit_service.record(
        db,
        actor_id=actor.id,
        action=f"publication.duplicate_{decision.action}",
        entity_type="publication_duplicate",
        entity_id=row.id,
        after={"status": target.value, **detail},
        ip=ip,
    )
    db.commit()
    db.refresh(row)
    return _read(db, row)


def _merge(db: Session, row: PublicationDuplicate, decision: DuplicateDecision) -> dict[str, Any]:
    if decision.keep_id is None:
        raise KeepIdRequiredError
    if row.publication_a_id is None or row.publication_b_id is None:
        raise PairIncompleteError
    if decision.keep_id not in (row.publication_a_id, row.publication_b_id):
        raise KeepIdNotInPairError

    loser_id = (
        row.publication_b_id if decision.keep_id == row.publication_a_id else row.publication_a_id
    )
    winner = db.get(Publication, decision.keep_id)
    loser = db.get(Publication, loser_id)
    if winner is None or loser is None:
        raise PairIncompleteError

    row.snapshot = _snapshot(db, loser)
    moved = _carry_over(db, loser, winner)
    inherited_doi = None
    if winner.doi is None and loser.doi is not None:
        inherited_doi = loser.doi

    # Flush the carried-over rows before the delete, so the cascade cannot
    # take an author slot that has just been reassigned.
    db.flush()
    db.delete(loser)
    db.flush()
    if inherited_doi is not None:
        # Only now is the unique DOI free to take.
        winner.doi = inherited_doi
    row.merged_into_id = winner.id
    return {"kept": str(winner.id), "removed": str(loser_id), **moved}


def undo_merge(
    db: Session, actor: User, duplicate_id: uuid.UUID, *, ip: str | None = None
) -> DuplicateRead:
    """Put back the record a merge removed.

    The restored publication gets a new id -- the row it had is gone -- so any
    link saved to the old one will not resolve. Everything else returns: the
    metadata, the author slots in their original order, and the project links.
    """
    row = db.get(PublicationDuplicate, duplicate_id)
    if row is None:
        raise DuplicateNotFoundError
    if row.status is not DuplicateStatus.MERGED or row.snapshot is None:
        raise NothingToUndoError
    assert_transition(row.status, DuplicateStatus.SUSPECTED)

    snapshot = cast(dict[str, Any], row.snapshot)
    restored = Publication(
        title=cast(str, snapshot["title"]),
        abstract=snapshot.get("abstract"),
        venue=snapshot.get("venue"),
        year=cast(int, snapshot["year"]),
        doi=snapshot.get("doi"),
        url=snapshot.get("url"),
        # Back to the enum: the snapshot holds its value as a string, and
        # assigning that raw would make `publication.pub_type.value` blow up
        # on the next read.
        pub_type=PublicationType(cast(str, snapshot["pub_type"])),
        created_by=uuid.UUID(cast(str, snapshot["created_by"])),
    )
    # The survivor may have inherited the DOI during the merge; it belongs to
    # the record being restored, and the column is unique.
    winner = db.get(Publication, row.merged_into_id) if row.merged_into_id else None
    if winner is not None and restored.doi is not None and winner.doi == restored.doi:
        winner.doi = None
        db.flush()
    db.add(restored)
    db.flush()

    for author in cast(list[dict[str, Any]], snapshot.get("authors", [])):
        db.add(
            PublicationAuthor(
                publication_id=restored.id,
                user_id=uuid.UUID(author["user_id"]) if author["user_id"] else None,
                external_name=author["external_name"],
                author_order=author["author_order"],
            )
        )
    for project_id in cast(list[str], snapshot.get("projects", [])):
        already = db.execute(
            select(ProjectPublication).where(
                ProjectPublication.project_id == uuid.UUID(project_id),
                ProjectPublication.publication_id == restored.id,
            )
        ).scalar_one_or_none()
        if already is None:
            db.add(ProjectPublication(project_id=uuid.UUID(project_id), publication_id=restored.id))

    removed_id = snapshot.get("id")
    row.publication_a_id, row.publication_b_id = _ordered(row.merged_into_id, restored.id)
    row.status = DuplicateStatus.SUSPECTED
    row.merged_into_id = None
    row.snapshot = None
    row.decided_by = actor.id
    row.decided_at = datetime.now(UTC)
    audit_service.record(
        db,
        actor_id=actor.id,
        action="publication.duplicate_merge_undone",
        entity_type="publication_duplicate",
        entity_id=row.id,
        before={"removed": removed_id},
        after={"restored_as": str(restored.id)},
        ip=ip,
    )
    db.commit()
    db.refresh(row)
    return _read(db, row)


def _ordered(left: uuid.UUID | None, right: uuid.UUID) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """Keep the pair in id order, which the CHECK constraint requires."""
    if left is None:
        return right, None
    return (left, right) if left < right else (right, left)


def pending_count(db: Session) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(PublicationDuplicate)
            .where(PublicationDuplicate.status == DuplicateStatus.SUSPECTED)
        ).scalar_one()
    )


__all__ = [
    "DuplicateNotFoundError",
    "KeepIdNotInPairError",
    "KeepIdRequiredError",
    "NothingToUndoError",
    "PairIncompleteError",
    "decide",
    "get_duplicate",
    "list_duplicates",
    "pending_count",
    "scan",
    "undo_merge",
]
