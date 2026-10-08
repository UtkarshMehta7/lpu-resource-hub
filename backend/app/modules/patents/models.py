"""Patents, their ordered inventor lists and links to projects.

A patent is **not** a publication, which is why this is its own table rather
than an eighth `publication_type`:

* It has a **lifecycle** that runs for years -- filed, published, granted,
  then lapsed or rejected. `publications` has no status column at all,
  because a paper does not change state after it appears.
* Its **identifiers are different**. There is no DOI; there is an application
  number, a pre-grant publication number and a grant number, each meaningful
  only inside a jurisdiction. The de-duplication rules are built on the DOI
  ("two different DOIs are never the same work") and have nothing to say here.
* It has an **assignee** -- usually the university -- which owns the right.
  No publication has an equivalent, and it is the commercially important
  field.
* Analytics counts `publications` with no type filter in nineteen modules.
  An eighth enum member would have silently folded patents into every
  publication count on the platform.

The things it genuinely shares with a publication -- an ordered list of
people, links to projects, a creator who may edit it -- are modelled the same
way deliberately, so the two read alike where they are alike.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.profiles.models import VerificationStatus


class PatentStatus(StrEnum):
    """Where the invention has got to, from disclosure through to grant.

    ADR 0035 first called this "what the patent office did", which was too
    narrow: the office is the second half of the journey, and the half that
    decides whether a patent ever exists happens here. An inventor discloses,
    the IP cell assesses, the university decides whether to file -- and only
    then does an office have an opinion. Modelling that as a separate table
    would have split one invention across two records and asked which of them
    owned the inventor list.

    Stored rather than derived. Derivation was considered -- a grant date
    implies a grant, the way a milestone's risk is derived from its dates
    (ADR 0026) -- but it cannot express DECLINED, REJECTED, WITHDRAWN or
    LAPSED, none of which has a date that distinguishes it from the others.

    The first four are the university's; the rest are the office's.
    """

    #: Submitted to the IP cell. The record exists, nothing is filed.
    DISCLOSED = "disclosed"
    #: The IP cell is assessing patentability and commercial merit.
    UNDER_ASSESSMENT = "under_assessment"
    #: The university has agreed to file. Nothing is lodged yet.
    APPROVED_TO_FILE = "approved_to_file"
    #: The university will not file. Terminal, with a reason recorded.
    DECLINED = "declined"
    FILED = "filed"
    PUBLISHED = "published"
    GRANTED = "granted"
    LAPSED = "lapsed"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class Patent(Base):
    __tablename__ = "patents"
    __table_args__ = (
        # A status that claims an event must carry that event's date. The same
        # shape as the milestones' "done is never undated" check.
        CheckConstraint(
            "status <> 'granted' OR grant_date IS NOT NULL",
            name="granted_has_a_grant_date",
        ),
        CheckConstraint(
            "status <> 'published' OR publication_date IS NOT NULL",
            name="published_has_a_publication_date",
        ),
        CheckConstraint("jurisdiction ~ '^[A-Z]{2}$'", name="jurisdiction_is_a_st3_code"),
        # Nothing before FILED has a filing date, and nothing from FILED
        # onwards lacks one. The pre-office stages are the university's own.
        CheckConstraint(
            # Cast to text, matching migration 0033: the enum literals cannot
            # be referenced in the transaction that adds them.
            "(status::text IN ('disclosed', 'under_assessment', 'approved_to_file', "
            "'declined')) = (filing_date IS NULL)",
            name="filing_date_exactly_when_filed",
        ),
        CheckConstraint(
            "status::text <> 'declined' OR assessment_note IS NOT NULL",
            name="declining_gives_a_reason",
        ),
        # A number is unique within the office that issued it and nowhere
        # else: IN 202141000001 and US 202141000001 are different patents.
        # Partial, because most records carry only some of the three.
        Index(
            "uq_patents_application_number",
            "jurisdiction",
            "application_number",
            unique=True,
            postgresql_where=text("application_number IS NOT NULL"),
        ),
        Index(
            "uq_patents_grant_number",
            "jurisdiction",
            "grant_number",
            unique=True,
            postgresql_where=text("grant_number IS NOT NULL"),
        ),
        Index("ix_patents_search_document", "search_document", postgresql_using="gin"),
        Index(
            "ix_patents_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: WIPO ST.3 code -- the patent office, not the country of the inventors.
    #: "IN", "US", "EP" (European Patent Office), "WO" (PCT application).
    jurisdiction: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    application_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    publication_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    grant_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Set when the application is actually lodged; it establishes priority.
    #: Null for everything still inside the university.
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    grant_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[PatentStatus] = mapped_column(
        Enum(
            PatentStatus,
            name="patent_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        index=True,
    )
    #: Who holds the right. Usually the university; sometimes a sponsor.
    assignee: Mapped[str | None] = mapped_column(String(300), nullable=True)
    #: The IP cell's docket, e.g. "LPU/IDF/2026/0007". Human-quotable, which
    #: is the whole point: an inventor chasing their disclosure says this, not
    #: a UUID. Allocated on disclosure and never reused.
    reference: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    #: What the invention solves, how, and why it is not obvious. Three
    #: questions rather than one description box, because an assessor reads
    #: for exactly these and a single box buries them.
    problem_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    novelty: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Prior art the inventor already knows of. Declaring it is a duty in most
    #: jurisdictions, and concealing it can invalidate a granted patent.
    known_prior_art: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: **The field that most often decides whether a patent is possible at
    #: all.** A paper, poster, thesis or demo before filing can destroy
    #: novelty outright; grace periods are narrow where they exist and absent
    #: in much of the world. Captured at disclosure so the IP cell sees it
    #: before it is too late to act on, not after.
    public_disclosure_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    public_disclosure_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Sponsor or grant. Public funding usually carries ownership and
    #: reporting obligations, and the IP cell has to know before it files.
    funding_source: Mapped[str | None] = mapped_column(String(300), nullable=True)
    commercial_potential: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Why the IP cell decided as it did. Required to decline: "no" without a
    #: reason is the thing that stops people disclosing next time.
    assessment_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Whether somebody senior has vouched for the RECORD -- a separate
    #: question from `status`, which is where the application has got to at
    #: the patent office. The office decides one; the institution decides the
    #: other, and a granted patent can still be recorded here wrongly.
    #:
    #: Reuses the `verification_status` enum the researcher profiles already
    #: use rather than minting a second one that would say the same four
    #: words. UNVERIFIED goes unused here: recording a patent IS asking for
    #: it to be checked, so a new record starts PENDING.
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(
            VerificationStatus,
            name="verification_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        server_default=VerificationStatus.PENDING.value,
        index=True,
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Why it was rejected, so the person is told something useful.
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_document: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(abstract, '')), 'B') || "
            "setweight(to_tsvector('english', coalesce(assignee, '')), 'C')",
            persisted=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PatentInventor(Base):
    """One inventor slot: a platform user, or an external name -- never both.

    Inventors, not authors. On a patent the distinction is legal rather than
    stylistic: an inventor is a person who contributed to the claims, and
    naming the wrong set can invalidate the grant.
    """

    __tablename__ = "patent_inventors"
    __table_args__ = (
        CheckConstraint("num_nonnulls(user_id, external_name) = 1", name="exactly_one_inventor"),
        CheckConstraint("inventor_order >= 1", name="inventor_order_positive"),
        UniqueConstraint("patent_id", "inventor_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    patent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SET NULL would violate the CHECK, so deleting a user deletes their
    # inventor slot; the rest of the list keeps its order.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    external_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    inventor_order: Mapped[int] = mapped_column(Integer, nullable=False)


class ProjectPatent(Base):
    __tablename__ = "project_patents"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    patent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patents.id", ondelete="CASCADE"), primary_key=True
    )
