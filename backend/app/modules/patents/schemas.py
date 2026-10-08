"""Pydantic schemas for patents.

`created_by`, `status` and every verification field are never
client-writable. Status moves through its own endpoint so the transition
table is the only way it can change; verification moves through another, so
that approving a record is visibly a different act from editing one.

Inventors are an ordered list: position in the list is the inventor order, so
a client cannot produce gaps or duplicate positions.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.patents.models import PatentStatus
from app.modules.profiles.models import VerificationStatus

_ST3 = re.compile(r"^[A-Z]{2}$")


class InventorInput(BaseModel):
    user_id: uuid.UUID | None = None
    external_name: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.user_id is None) == (self.external_name is None):
            raise ValueError("each inventor needs exactly one of user_id or external_name")
        return self


class _PatentFields(BaseModel):
    abstract: str | None = Field(default=None, max_length=20000)
    assignee: str | None = Field(default=None, max_length=300)
    application_number: str | None = Field(default=None, max_length=64)
    url: str | None = Field(default=None, max_length=2000)

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return value


class PatentCreate(_PatentFields):
    title: str = Field(min_length=1, max_length=500)
    jurisdiction: str = Field(min_length=2, max_length=2)
    filing_date: date
    inventors: list[InventorInput] = Field(min_length=1, max_length=100)
    project_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("jurisdiction")
    @classmethod
    def _upper_st3(cls, value: str) -> str:
        code = value.strip().upper()
        if not _ST3.match(code):
            raise ValueError("jurisdiction must be a two-letter patent office code, e.g. IN")
        return code


class PatentUpdate(_PatentFields):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    filing_date: date | None = None
    inventors: list[InventorInput] | None = Field(default=None, min_length=1, max_length=100)
    project_ids: list[uuid.UUID] | None = None


class PatentTransition(BaseModel):
    """A move along the patent office's lifecycle.

    `on` and `number` are what the office issued with the move: a publication
    date and number, or a grant date and number. Required for the statuses
    that cannot exist without them -- the database says the same thing with a
    CHECK, and this is what turns that into a sentence.
    """

    status: PatentStatus
    on: date | None = None
    number: str | None = Field(default=None, max_length=64)


class PatentDecision(BaseModel):
    """A coordinator's verdict on whether the RECORD is right."""

    decision: bool
    note: str | None = Field(default=None, max_length=2000)


class InventorRead(BaseModel):
    user_id: uuid.UUID | None
    name: str
    registration_number: str | None
    inventor_order: int


class LinkedProject(BaseModel):
    id: uuid.UUID
    title: str


class PatentRead(BaseModel):
    id: uuid.UUID
    title: str
    abstract: str | None
    jurisdiction: str
    application_number: str | None
    publication_number: str | None
    grant_number: str | None
    filing_date: date
    publication_date: date | None
    grant_date: date | None
    status: PatentStatus
    assignee: str | None
    url: str | None
    created_by: uuid.UUID
    creator_name: str
    verification_status: VerificationStatus
    verified_by: uuid.UUID | None
    verified_by_name: str | None
    verified_at: datetime | None
    verification_note: str | None
    inventors: list[InventorRead]
    projects: list[LinkedProject]
    #: The statuses this record may move to next, so the interface never
    #: offers a button the service would refuse.
    next_statuses: list[PatentStatus]
    created_at: datetime


# --- prior art ---------------------------------------------------------------


class SimilarPatent(BaseModel):
    """A patent already recorded here that looks like the one being filed."""

    id: uuid.UUID
    title: str
    jurisdiction: str
    status: PatentStatus
    filing_date: date
    grant_number: str | None
    score: float


class RelatedWork(BaseModel):
    """Published literature that may be prior art.

    A paper is prior art in exactly the way another patent is, and it is what
    most often destroys novelty -- which is lucky, because the open indexes
    cover papers and no open index covers patents.
    """

    title: str
    venue: str | None
    year: int | None
    doi: str | None
    url: str | None
    source: str


class RegistrySearch(BaseModel):
    """A worldwide register, with this query already built into the link."""

    name: str
    description: str
    url: str


class PriorArtResult(BaseModel):
    searched: str
    similar_patents: list[SimilarPatent]
    related_works: list[RelatedWork]
    registries: list[RegistrySearch]
    #: True when an external index could not be reached. The caller must say
    #: so rather than present a short list as a clean result.
    literature_unavailable: bool


class PriorArtQuery(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    abstract: str | None = Field(default=None, max_length=20000)
