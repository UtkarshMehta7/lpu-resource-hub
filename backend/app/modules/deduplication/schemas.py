"""Request and response shapes for the duplicate review queue."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.deduplication.models import DuplicateStatus


class PublicationSide(BaseModel):
    """One half of a suspected pair, as much as a reviewer needs to judge.

    Includes the DOI and URL so the claim can be checked at the source before
    anything is merged, which is the same principle the importer follows --
    every imported work links out so it can be verified rather than audited
    afterwards.
    """

    id: uuid.UUID
    title: str
    doi: str | None
    url: str | None
    venue: str | None
    year: int | None
    pub_type: str
    authors: list[str]
    #: What a merge here would carry over, so the cost is visible first --
    #: the same reasoning as the deletion-impact endpoint.
    project_count: int
    created_at: datetime


class DuplicateRead(BaseModel):
    id: uuid.UUID
    status: DuplicateStatus
    score: float
    evidence: dict[str, object]
    #: Absent once a merge has removed one side, or if a record was deleted
    #: outright. The decision stays readable either way.
    publication_a: PublicationSide | None
    publication_b: PublicationSide | None
    merged_into_id: uuid.UUID | None
    #: True when this row can be undone -- a merge whose snapshot is intact.
    can_undo: bool
    decided_by: uuid.UUID | None
    decided_by_name: str | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime


class DuplicateDecision(BaseModel):
    """What to do about a pair.

    `keep_id` is required for a merge and ignored otherwise: which record
    survives is a judgement about which is better described, and guessing it
    (by date, say) would silently discard the better record half the time.
    """

    action: Literal["merge", "separate", "ignore"]
    keep_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=2000)


class ScanResult(BaseModel):
    """What a scan found. Idempotent: running it twice adds nothing."""

    examined: int
    pairs_found: int
    pairs_new: int
    #: Pairs already decided are not resurrected by a later scan -- a
    #: reviewer's "these are different" must not come back next week.
    pairs_already_decided: int
