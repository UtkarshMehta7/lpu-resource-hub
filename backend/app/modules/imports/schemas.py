"""Request and response shapes for profile import."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.modules.imports.service import IMPORTABLE_FIELDS


class CandidateSearchRequest(BaseModel):
    """Find people who might be the caller, for them to choose between."""

    name: str = Field(min_length=2, max_length=200)
    affiliation: str | None = Field(default=None, max_length=200)


class AuthorCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    source_id: str
    #: Links to the record itself, so a choice can be checked, not guessed.
    source_url: str | None
    full_name: str
    affiliation: str | None
    other_affiliations: list[str]
    orcid: str | None
    works_count: int | None
    cited_by_count: int | None
    h_index: int | None
    topics: list[str]


class ImportLookupRequest(BaseModel):
    """What the researcher gives us to find themselves with.

    An ORCID iD is the reliable route. A name is accepted as a fallback for
    researchers who have not registered one, and the preview labels those
    results as unconfirmed.
    """

    orcid: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, max_length=200)
    affiliation: str | None = Field(default=None, max_length=200)
    #: `source_id` of a candidate the researcher picked. Wins over the name.
    openalex_author_id: str | None = Field(default=None, max_length=64)


class ImportApplyRequest(ImportLookupRequest):
    # Profile fields to bring in. Anything not listed here is left alone.
    fields: list[str] = Field(default_factory=list, max_length=len(IMPORTABLE_FIELDS))
    # `key` values from the preview's work list.
    work_keys: list[str] = Field(default_factory=list, max_length=500)


class FieldSuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field: str
    current: str | None
    incoming: str | None
    changed: bool


class WorkCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    title: str
    doi: str | None
    venue: str | None
    year: int | None
    pub_type: str
    abstract: str | None
    url: str | None
    authors: list[str]
    sources: list[str]
    status: str
    matched_publication_id: uuid.UUID | None
    matched_title: str | None
    similarity: float | None
    reason: str | None
    importable: bool


class ImportPreviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    orcid: str | None
    sources_used: list[str]
    source_errors: dict[str, str]
    source_urls: dict[str, str]
    full_name: str | None
    affiliation: str | None
    metrics: dict[str, int]
    fields: list[FieldSuggestionRead]
    topics: list[str]
    works: list[WorkCandidateRead]
    new_count: int
    known_count: int


class ImportResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    import_id: uuid.UUID
    applied_fields: list[str]
    works_imported: int
    works_skipped: int
    works_failed: int
    source_errors: dict[str, str]
    verification_reset: bool


class ImportHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    orcid_id: str | None
    works_found: int
    works_imported: int
    works_already_known: int
    applied_fields: list[str]
    created_at: object


__all__ = [
    "AuthorCandidateRead",
    "CandidateSearchRequest",
    "ImportApplyRequest",
    "ImportHistoryRead",
    "ImportLookupRequest",
    "ImportPreviewRead",
    "ImportResultRead",
    "WorkCandidateRead",
]
