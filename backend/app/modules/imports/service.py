"""Fetching, previewing and applying a profile import.

The flow is deliberately two-step. `preview` reads the external sources and
reports what it found, changing nothing. `apply` re-reads them and writes only
the items the researcher ticked.

Re-reading on apply looks wasteful, and is on purpose: it means the
bibliographic data written to the register always comes from the source, never
from the browser. If apply trusted the payload the client sent back, anyone
could post arbitrary publications under an "imported from Crossref" banner.
An import takes a few seconds and happens rarely; the guarantee is worth it.

Nothing here is destructive. A field the researcher already filled in is never
overwritten unless they tick it, and a publication already in the register is
reported, never duplicated and never edited.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.imports.connectors import (
    AuthorCandidate,
    ConnectorError,
    CrossrefConnector,
    ExternalProfile,
    ExternalWork,
    OpenAlexConnector,
    OrcidConnector,
    ProfileQuery,
    SemanticScholarConnector,
    build_client,
    normalise_orcid,
)
from app.modules.imports.merge import (
    TITLE_MATCH_THRESHOLD,
    TITLE_SUGGEST_THRESHOLD,
    MergedProfile,
    MergedWork,
    merge_profiles,
    title_similarity,
)
from app.modules.imports.models import ProfileImport
from app.modules.profiles.models import ResearcherProfile, VerificationStatus
from app.modules.publications.models import MAX_YEAR, MIN_YEAR, Publication, PublicationType
from app.modules.publications.schemas import AuthorInput, PublicationCreate
from app.modules.publications.service import DuplicateDoiError, create_publication
from app.modules.users.models import User

logger = logging.getLogger(__name__)

# How many existing publications the trigram shortlist may return per title.
CANDIDATE_LIMIT = 5

# Profile fields a researcher may choose to bring in. `designation` and `bio`
# overwrite; `links` merges. Nothing else on the profile is importable --
# availability, verification status and department are decisions this
# institution makes, not facts an external site can assert.
IMPORTABLE_FIELDS = ("designation", "bio", "links")


class ImportDisabledError(Exception):
    """Profile import is switched off for this deployment."""


class NoProfileError(Exception):
    """The caller has no researcher profile to import into."""


class NothingFoundError(Exception):
    """No source recognised the researcher."""


class OrcidTakenError(Exception):
    """Another account has already claimed that ORCID iD."""


@dataclass(frozen=True, slots=True)
class WorkCandidate:
    key: str
    title: str
    doi: str | None
    venue: str | None
    year: int | None
    pub_type: str
    abstract: str | None
    #: Where to read the work itself. The DOI is preferred where there is one,
    #: but books, theses and older papers often have only this.
    url: str | None
    authors: tuple[str, ...]
    sources: tuple[str, ...]
    # "new" | "already_in_register" | "possible_duplicate" | "not_importable"
    status: str
    matched_publication_id: uuid.UUID | None = None
    matched_title: str | None = None
    similarity: float | None = None
    reason: str | None = None

    @property
    def importable(self) -> bool:
        return self.status in ("new", "possible_duplicate")


@dataclass(frozen=True, slots=True)
class FieldSuggestion:
    field: str
    current: str | None
    incoming: str | None
    changed: bool


@dataclass(slots=True)
class ImportPreview:
    orcid: str | None
    sources_used: list[str] = field(default_factory=list)
    source_errors: dict[str, str] = field(default_factory=dict)
    source_urls: dict[str, str] = field(default_factory=dict)
    full_name: str | None = None
    affiliation: str | None = None
    metrics: dict[str, int] = field(default_factory=dict)
    fields: list[FieldSuggestion] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    works: list[WorkCandidate] = field(default_factory=list)

    @property
    def new_count(self) -> int:
        return sum(1 for w in self.works if w.status == "new")

    @property
    def known_count(self) -> int:
        return sum(1 for w in self.works if w.status == "already_in_register")


@dataclass(slots=True)
class ImportResult:
    import_id: uuid.UUID
    applied_fields: list[str]
    works_imported: int
    works_skipped: int
    works_failed: int
    source_errors: dict[str, str]
    #: True when the import sent an already-verified profile back for review.
    verification_reset: bool = False


# --------------------------------------------------------------------- fetch


def _gather(query: ProfileQuery) -> tuple[MergedProfile, dict[str, str]]:
    """Read every source and fold the answers into one candidate profile.

    A source that fails is recorded and skipped: three sources answering is a
    good import, and one site being down should not stop it.
    """
    settings = get_settings()
    errors: dict[str, str] = {}
    profiles: list[ExternalProfile] = []
    works: list[ExternalWork] = []

    orcid = OrcidConnector()
    openalex = OpenAlexConnector(settings.import_contact_email)
    crossref = CrossrefConnector(settings.import_contact_email)
    scholar = SemanticScholarConnector()

    with build_client(settings.import_contact_email) as client:
        # ORCID first: it is the only source that resolves identity rather
        # than guessing it, and the name it returns disambiguates the rest.
        resolved = ProfileQuery(
            orcid=query.orcid,
            name=query.name,
            affiliation=query.affiliation,
            openalex_author_id=query.openalex_author_id,
        )
        for connector in (orcid, openalex):
            try:
                found = connector.fetch(client, resolved)
            except ConnectorError as exc:
                errors[connector.name] = str(exc)
                continue
            if found is None:
                continue
            profiles.append(found)
            works.extend(found.works)
            if connector is orcid and found.full_name and not resolved.name:
                resolved = ProfileQuery(
                    orcid=resolved.orcid,
                    name=found.full_name,
                    affiliation=found.affiliation or resolved.affiliation,
                    openalex_author_id=resolved.openalex_author_id,
                )

        # Enrichment: both are keyed by DOI, so they add detail to works we
        # already have rather than discovering new ones.
        dois = [w.doi for w in works if w.doi]
        for enricher in (crossref, scholar):
            if not dois:
                break
            try:
                works.extend(enricher.enrich(client, dois).values())
            except ConnectorError as exc:
                errors[enricher.name] = str(exc)

    return merge_profiles(profiles, works), errors


# ----------------------------------------------------------------- dedup


def _pub_type(raw: str | None) -> PublicationType:
    text = (raw or "").replace("_", "-").casefold()
    if text in ("journal-article", "article", "journalarticle", "article-journal"):
        return PublicationType.JOURNAL_ARTICLE
    if text in ("proceedings-article", "conference-paper", "conference", "conferencepaper"):
        return PublicationType.CONFERENCE_PAPER
    if text in ("book-chapter", "chapter", "bookchapter"):
        return PublicationType.BOOK_CHAPTER
    if text in ("book", "monograph", "edited-book"):
        return PublicationType.BOOK
    if text in ("preprint", "posted-content"):
        return PublicationType.PREPRINT
    if text in ("dissertation", "thesis"):
        return PublicationType.THESIS
    return PublicationType.OTHER


def _candidate(
    work: MergedWork,
    status: str,
    *,
    matched_publication_id: uuid.UUID | None = None,
    matched_title: str | None = None,
    similarity: float | None = None,
    reason: str | None = None,
) -> WorkCandidate:
    """Build a candidate from a merged work plus the verdict about it.

    Written out rather than unpacked from a dict so the field types survive:
    `**base` collapses to dict[str, object] and loses every one of them.
    """
    return WorkCandidate(
        key=work.key,
        title=work.title,
        doi=work.doi,
        venue=work.venue,
        year=work.year,
        pub_type=_pub_type(work.pub_type).value,
        abstract=work.abstract,
        url=work.url,
        authors=work.authors,
        sources=work.sources,
        status=status,
        matched_publication_id=matched_publication_id,
        matched_title=matched_title,
        similarity=similarity,
        reason=reason,
    )


def _classify(db: Session, work: MergedWork) -> WorkCandidate:
    if work.year is None or not (MIN_YEAR <= work.year <= MAX_YEAR):
        return _candidate(
            work,
            "not_importable",
            reason="The register needs a publication year and this record has none.",
        )

    # Rule 1: a DOI already in the register is the same work, decisively.
    if work.doi:
        existing = db.execute(
            select(Publication.id, Publication.title).where(
                func.lower(Publication.doi) == work.doi.lower()
            )
        ).first()
        if existing is not None:
            return _candidate(
                work,
                "already_in_register",
                matched_publication_id=existing.id,
                matched_title=existing.title,
                similarity=100.0,
                reason="Already in the register, matched on DOI.",
            )

    # Rule 2: shortlist by trigram (index-backed), then score properly.
    candidates = db.execute(
        select(Publication.id, Publication.title, Publication.doi)
        .where(Publication.title.op("%")(work.title))
        .limit(CANDIDATE_LIMIT)
    ).all()

    best_id: uuid.UUID | None = None
    best_title: str | None = None
    best_score = 0.0
    for row in candidates:
        # Two different DOIs are two different works however alike the titles.
        if work.doi and row.doi and row.doi.lower() != work.doi.lower():
            continue
        score = title_similarity(work.title, row.title)
        if score > best_score:
            best_id, best_title, best_score = row.id, row.title, score

    if best_id is not None and best_score >= TITLE_MATCH_THRESHOLD:
        return _candidate(
            work,
            "already_in_register",
            matched_publication_id=best_id,
            matched_title=best_title,
            similarity=round(best_score, 1),
            reason=f"Title matches an existing entry at {best_score:.0f}%.",
        )
    if best_id is not None and best_score >= TITLE_SUGGEST_THRESHOLD:
        return _candidate(
            work,
            "possible_duplicate",
            matched_publication_id=best_id,
            matched_title=best_title,
            similarity=round(best_score, 1),
            reason=f"Looks close to an existing entry ({best_score:.0f}%) -- please check.",
        )
    return _candidate(work, "new")


# --------------------------------------------------------------------- api


def _profile_for(db: Session, user: User) -> ResearcherProfile:
    profile = db.scalar(select(ResearcherProfile).where(ResearcherProfile.user_id == user.id))
    if profile is None:
        raise NoProfileError
    return profile


def _guard_orcid(db: Session, user: User, orcid: str | None) -> None:
    if orcid is None:
        return
    taken = db.scalar(
        select(ResearcherProfile.user_id).where(
            ResearcherProfile.orcid_id == orcid, ResearcherProfile.user_id != user.id
        )
    )
    if taken is not None:
        raise OrcidTakenError


class InvalidOrcidError(Exception):
    """The caller sent something that is not an ORCID iD."""


def search_candidates(
    db: Session, user: User, name: str, affiliation: str | None
) -> list[AuthorCandidate]:
    """People who might be the caller, for them to choose between.

    Exists because a name is not an identifier. Searching "Nitish Kumar"
    returns a Nitish Srivastava at Google before it returns either actual
    Nitish Kumar, and silently importing the first hit attributes a
    stranger's entire publication list to somebody else.
    """
    settings = get_settings()
    if not settings.import_enabled:
        raise ImportDisabledError
    _profile_for(db, user)
    connector = OpenAlexConnector(settings.import_contact_email)
    with build_client(settings.import_contact_email) as client:
        try:
            return connector.search_candidates(client, name, affiliation)
        except ConnectorError:
            return []


def build_query(
    orcid: str | None,
    name: str | None,
    affiliation: str | None,
    openalex_author_id: str | None = None,
) -> ProfileQuery:
    """Validate and normalise the lookup before any source is contacted.

    A malformed iD is rejected here rather than inside ProfileQuery, so the
    caller gets a 422 explaining the format instead of a 500 from a dataclass
    invariant.
    """
    cleaned = normalise_orcid(orcid) if orcid else None
    if orcid and cleaned is None:
        raise InvalidOrcidError
    if cleaned is None and not name and not openalex_author_id:
        raise InvalidOrcidError
    return ProfileQuery(
        orcid=cleaned,
        name=name,
        affiliation=affiliation,
        openalex_author_id=openalex_author_id,
    )


def preview(db: Session, user: User, query: ProfileQuery) -> ImportPreview:
    settings = get_settings()
    if not settings.import_enabled:
        raise ImportDisabledError
    profile = _profile_for(db, user)
    _guard_orcid(db, user, query.orcid)

    merged, errors = _gather(query)
    if not merged.sources:
        raise NothingFoundError

    current = {
        "designation": profile.designation,
        "bio": profile.bio,
        "links": _links_summary(profile.links),
    }
    incoming = {
        "designation": merged.designation,
        "bio": merged.bio,
        "links": _links_summary([{"label": a, "url": b} for a, b in merged.links]) or None,
    }
    suggestions = [
        FieldSuggestion(
            field=name,
            current=current[name],
            incoming=incoming[name],
            changed=bool(incoming[name]) and incoming[name] != current[name],
        )
        for name in IMPORTABLE_FIELDS
    ]

    return ImportPreview(
        orcid=query.orcid,
        sources_used=list(merged.sources),
        source_errors=errors,
        source_urls=dict(merged.source_urls),
        full_name=merged.full_name,
        affiliation=merged.affiliation,
        metrics=dict(merged.metrics),
        fields=suggestions,
        topics=list(merged.topics[:20]),
        works=[_classify(db, work) for work in merged.works],
    )


def apply(
    db: Session,
    user: User,
    query: ProfileQuery,
    *,
    fields: Sequence[str],
    work_keys: Sequence[str],
) -> ImportResult:
    settings = get_settings()
    if not settings.import_enabled:
        raise ImportDisabledError
    profile = _profile_for(db, user)
    _guard_orcid(db, user, query.orcid)

    merged, errors = _gather(query)
    if not merged.sources:
        raise NothingFoundError

    wanted_fields = [name for name in fields if name in IMPORTABLE_FIELDS]
    applied: list[str] = []
    if "designation" in wanted_fields and merged.designation:
        profile.designation = merged.designation[:150]
        applied.append("designation")
    if "bio" in wanted_fields and merged.bio:
        profile.bio = merged.bio
        applied.append("bio")
    if "links" in wanted_fields and merged.links:
        profile.links = _merge_links(profile.links, merged.links)
        applied.append("links")
    if query.orcid:
        profile.orcid_id = query.orcid
        profile.orcid_last_imported_at = datetime.now(UTC)

    wanted_keys = set(work_keys)
    imported = skipped = failed = 0
    for work in merged.works:
        if work.key not in wanted_keys:
            continue
        candidate = _classify(db, work)
        if not candidate.importable:
            skipped += 1
            continue
        try:
            create_publication(db, user, _to_create(user, work, candidate))
            imported += 1
        except DuplicateDoiError:
            # Someone added the same DOI between the preview and now.
            skipped += 1
        except Exception:  # noqa: BLE001 - one bad record must not lose the rest
            logger.exception("profile import: could not create publication %r", work.title[:80])
            db.rollback()
            failed += 1

    # An import puts externally-sourced claims on a profile somebody already
    # signed off. Nobody here has checked those claims, so a verified profile
    # goes back in the queue rather than keeping a tick it no longer earned.
    # An unverified profile is left exactly where it is.
    verification_reset = False
    if (applied or imported) and profile.verification_status is VerificationStatus.VERIFIED:
        profile.verification_status = VerificationStatus.PENDING
        profile.verified_by = None
        profile.verified_at = None
        verification_reset = True

    record = ProfileImport(
        user_id=user.id,
        orcid_id=query.orcid,
        sources={"used": list(merged.sources), "failed": errors},
        applied_fields=applied,
        works_found=len(merged.works),
        works_imported=imported,
        works_already_known=sum(
            1 for w in merged.works if _classify(db, w).status == "already_in_register"
        ),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return ImportResult(
        import_id=record.id,
        applied_fields=applied,
        works_imported=imported,
        works_skipped=skipped,
        works_failed=failed,
        source_errors=errors,
        verification_reset=verification_reset,
    )


def _to_create(user: User, work: MergedWork, candidate: WorkCandidate) -> PublicationCreate:
    """Build the register entry, with the importing researcher as an author.

    The external author list is kept as plain names except for the researcher
    themselves, who is linked by id. Matching the other names to accounts is
    author disambiguation, and guessing it wrong attributes someone else's work
    -- so it is left to the researcher to do by hand afterwards.
    """
    authors: list[AuthorInput] = [AuthorInput(user_id=user.id)]
    own = (user.full_name or "").casefold()
    for name in work.authors:
        if name.casefold() == own:
            continue
        authors.append(AuthorInput(external_name=name[:200]))
    return PublicationCreate(
        title=work.title[:500],
        abstract=work.abstract,
        venue=work.venue,
        year=work.year or MIN_YEAR,
        doi=work.doi,
        url=work.url,
        pub_type=PublicationType(candidate.pub_type),
        authors=authors[:100],
        project_ids=[],
    )


def _links_summary(links: object) -> str | None:
    if not isinstance(links, list) or not links:
        return None
    parts = []
    for entry in links:
        if isinstance(entry, dict):
            label = str(entry.get("label") or "").strip()
            url = str(entry.get("url") or "").strip()
            if url:
                parts.append(f"{label or 'Link'}: {url}")
    return "; ".join(parts) or None


def _merge_links(
    existing: list[dict[str, str]] | None, incoming: tuple[tuple[str, str], ...]
) -> list[dict[str, str]]:
    merged = list(existing or [])
    seen = {str(entry.get("url")) for entry in merged if isinstance(entry, dict)}
    for label, url in incoming:
        if url not in seen:
            merged.append({"label": label, "url": url})
            seen.add(url)
    return merged[:20]


__all__ = [
    "IMPORTABLE_FIELDS",
    "ImportDisabledError",
    "InvalidOrcidError",
    "ImportPreview",
    "ImportResult",
    "NoProfileError",
    "NothingFoundError",
    "OrcidTakenError",
    "WorkCandidate",
    "apply",
    "build_query",
    "preview",
]
