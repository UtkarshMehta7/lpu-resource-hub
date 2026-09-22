"""Publications: CRUD, ordered author lists, project links, listing.

Publications themselves are public to every signed-in user (they are
published work). What is *not* public is the projects they link to: a linked
project is only shown to viewers who may see that project, so linking a
publication to a draft can't leak the draft's title. Services never import
FastAPI.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams
from app.modules.audit import service as audit_service
from app.modules.projects.models import Project, ProjectMember, ProjectResearchArea
from app.modules.projects.policies import visibility_filter
from app.modules.publications.models import (
    ProjectPublication,
    Publication,
    PublicationAuthor,
)
from app.modules.publications.schemas import (
    AuthorInput,
    AuthorRead,
    LinkedProject,
    PublicationCreate,
    PublicationRead,
    PublicationUpdate,
)
from app.modules.taxonomy.models import ResearchArea
from app.modules.users.models import User, UserRole


class PublicationNotFoundError(Exception):
    """No publication with this id."""


class NotCreatorError(Exception):
    """Only the creator (or an admin, for deletion) may change a publication."""


class DuplicateDoiError(Exception):
    """Another publication already has this DOI."""


class UnknownAuthorError(Exception):
    """An author's user_id doesn't name an active user."""


class ProjectLinkError(Exception):
    """A linked project doesn't exist, or the creator neither owns nor belongs to it."""


# --- validation --------------------------------------------------------------


def _validate_authors(db: Session, authors: Sequence[AuthorInput]) -> None:
    user_ids = {a.user_id for a in authors if a.user_id is not None}
    if not user_ids:
        return
    found = set(
        db.execute(select(User.id).where(User.id.in_(user_ids), User.is_active.is_(True))).scalars()
    )
    if user_ids - found:
        raise UnknownAuthorError


def _validate_project_links(db: Session, actor: User, project_ids: Sequence[uuid.UUID]) -> None:
    """You may only link a publication to projects you own or are a member of."""
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


def _replace_authors(
    db: Session, publication_id: uuid.UUID, authors: Sequence[AuthorInput]
) -> None:
    db.execute(delete(PublicationAuthor).where(PublicationAuthor.publication_id == publication_id))
    db.flush()
    db.add_all(
        PublicationAuthor(
            publication_id=publication_id,
            user_id=author.user_id,
            external_name=author.external_name,
            author_order=position,
        )
        for position, author in enumerate(authors, start=1)
    )


def _replace_links(
    db: Session, publication_id: uuid.UUID, project_ids: Sequence[uuid.UUID]
) -> None:
    db.execute(
        delete(ProjectPublication).where(ProjectPublication.publication_id == publication_id)
    )
    db.add_all(
        ProjectPublication(project_id=pid, publication_id=publication_id)
        for pid in set(project_ids)
    )


def _commit_or_duplicate_doi(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "doi" in str(exc.orig).lower():
            raise DuplicateDoiError from exc
        raise


# --- building responses ------------------------------------------------------


def _authors(db: Session, publication_id: uuid.UUID) -> list[AuthorRead]:
    rows = db.execute(
        select(PublicationAuthor, User.full_name)
        .outerjoin(User, User.id == PublicationAuthor.user_id)
        .where(PublicationAuthor.publication_id == publication_id)
        .order_by(PublicationAuthor.author_order)
    ).all()
    return [
        AuthorRead(
            user_id=author.user_id,
            name=full_name if author.user_id is not None else (author.external_name or ""),
            author_order=author.author_order,
        )
        for author, full_name in rows
    ]


def _visible_projects(db: Session, viewer: User, publication_id: uuid.UUID) -> list[LinkedProject]:
    rows = db.execute(
        select(Project.id, Project.title)
        .join(ProjectPublication, ProjectPublication.project_id == Project.id)
        .where(
            ProjectPublication.publication_id == publication_id,
            Project.deleted_at.is_(None),
            visibility_filter(viewer),
        )
        .order_by(Project.title)
    ).all()
    return [LinkedProject(id=pid, title=title) for pid, title in rows]


def _to_read(db: Session, viewer: User, publication: Publication) -> PublicationRead:
    return PublicationRead(
        id=publication.id,
        title=publication.title,
        abstract=publication.abstract,
        venue=publication.venue,
        year=publication.year,
        doi=publication.doi,
        url=publication.url,
        pub_type=publication.pub_type,
        created_by=publication.created_by,
        authors=_authors(db, publication.id),
        projects=_visible_projects(db, viewer, publication.id),
        created_at=publication.created_at,
    )


def _load(db: Session, publication_id: uuid.UUID) -> Publication:
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise PublicationNotFoundError
    return publication


# --- operations --------------------------------------------------------------


def create_publication(db: Session, creator: User, data: PublicationCreate) -> PublicationRead:
    _validate_authors(db, data.authors)
    _validate_project_links(db, creator, data.project_ids)
    publication = Publication(
        title=data.title,
        abstract=data.abstract,
        venue=data.venue,
        year=data.year,
        doi=data.doi,
        url=data.url,
        pub_type=data.pub_type,
        created_by=creator.id,
    )
    db.add(publication)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateDoiError from exc
    _replace_authors(db, publication.id, data.authors)
    _replace_links(db, publication.id, data.project_ids)
    _commit_or_duplicate_doi(db)
    db.refresh(publication)
    return _to_read(db, creator, publication)


def get_publication(db: Session, viewer: User, publication_id: uuid.UUID) -> PublicationRead:
    return _to_read(db, viewer, _load(db, publication_id))


def update_publication(
    db: Session, actor: User, publication_id: uuid.UUID, data: PublicationUpdate
) -> PublicationRead:
    publication = _load(db, publication_id)
    if publication.created_by != actor.id:
        raise NotCreatorError

    if data.authors is not None:
        _validate_authors(db, data.authors)
    if data.project_ids is not None:
        _validate_project_links(db, actor, data.project_ids)

    for field in ("title", "year", "pub_type"):
        value = getattr(data, field)
        if value is not None:
            setattr(publication, field, value)
    for field in ("abstract", "venue", "doi", "url"):
        if field in data.model_fields_set:
            setattr(publication, field, getattr(data, field))

    if data.authors is not None:
        _replace_authors(db, publication.id, data.authors)
    if data.project_ids is not None:
        _replace_links(db, publication.id, data.project_ids)
    _commit_or_duplicate_doi(db)
    db.refresh(publication)
    return _to_read(db, actor, publication)


def delete_publication(
    db: Session, actor: User, publication_id: uuid.UUID, *, ip: str | None
) -> None:
    publication = _load(db, publication_id)
    is_creator = publication.created_by == actor.id
    if not is_creator and actor.role is not UserRole.ADMIN:
        raise NotCreatorError
    if not is_creator:
        audit_service.record(
            db,
            actor_id=actor.id,
            action="publication.deleted",
            entity_type="publication",
            entity_id=publication.id,
            before={"title": publication.title, "created_by": str(publication.created_by)},
            after=None,
            ip=ip,
        )
    db.delete(publication)
    db.commit()


def list_publications(
    db: Session,
    viewer: User,
    params: PageParams,
    *,
    q: str | None = None,
    author_id: uuid.UUID | None = None,
    year: int | None = None,
    project_id: uuid.UUID | None = None,
    research_area_id: uuid.UUID | None = None,
) -> Page[PublicationRead]:
    query = select(Publication)
    if q:
        query = query.where(
            Publication.search_document.op("@@")(func.websearch_to_tsquery("english", q))
        )
    if author_id is not None:
        # "Their publications": ones they're an author on, or created.
        query = query.where(
            or_(
                Publication.created_by == author_id,
                Publication.id.in_(
                    select(PublicationAuthor.publication_id).where(
                        PublicationAuthor.user_id == author_id
                    )
                ),
            )
        )
    if year is not None:
        query = query.where(Publication.year == year)
    visible_projects = select(Project.id).where(
        Project.deleted_at.is_(None), visibility_filter(viewer)
    )
    if project_id is not None:
        # Filtering by a project you can't see behaves as if it had none.
        query = query.where(
            Publication.id.in_(
                select(ProjectPublication.publication_id).where(
                    ProjectPublication.project_id == project_id,
                    ProjectPublication.project_id.in_(visible_projects),
                )
            )
        )
    if research_area_id is not None:
        area_ids = select(ResearchArea.id).where(
            or_(ResearchArea.id == research_area_id, ResearchArea.parent_id == research_area_id)
        )
        query = query.where(
            Publication.id.in_(
                select(ProjectPublication.publication_id).where(
                    ProjectPublication.project_id.in_(visible_projects),
                    ProjectPublication.project_id.in_(
                        select(ProjectResearchArea.project_id).where(
                            ProjectResearchArea.research_area_id.in_(area_ids)
                        )
                    ),
                )
            )
        )

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    if q:
        tsquery = func.websearch_to_tsquery("english", q)
        query = query.order_by(func.ts_rank(Publication.search_document, tsquery).desc())
    query = query.order_by(Publication.year.desc(), Publication.title)
    rows = db.execute(query.offset(params.offset).limit(params.page_size)).scalars().all()
    return Page[PublicationRead](
        items=[_to_read(db, viewer, publication) for publication in rows],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )
