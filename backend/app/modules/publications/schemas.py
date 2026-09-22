"""Pydantic schemas for publications.

created_by is never client-writable. Authors are an ordered list: position
in the list is the author order, so clients can't produce gaps or
duplicate positions.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.publications.models import MAX_YEAR, MIN_YEAR, PublicationType


class AuthorInput(BaseModel):
    user_id: uuid.UUID | None = None
    external_name: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.user_id is None) == (self.external_name is None):
            raise ValueError("each author needs exactly one of user_id or external_name")
        return self


class _DoiAndUrl(BaseModel):
    doi: str | None = Field(default=None, max_length=255)
    url: str | None = Field(default=None, max_length=2000)

    @field_validator("doi")
    @classmethod
    def _normalise_doi(cls, value: str | None) -> str | None:
        """Lower-case and strip resolver prefixes so duplicates are caught."""
        if value is None:
            return None
        doi = value.strip().lower()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            doi = doi.removeprefix(prefix)
        return doi or None

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return value


class PublicationCreate(_DoiAndUrl):
    title: str = Field(min_length=1, max_length=500)
    abstract: str | None = Field(default=None, max_length=20000)
    venue: str | None = Field(default=None, max_length=300)
    year: int = Field(ge=MIN_YEAR, le=MAX_YEAR)
    pub_type: PublicationType
    authors: list[AuthorInput] = Field(min_length=1, max_length=100)
    project_ids: list[uuid.UUID] = Field(default_factory=list)


class PublicationUpdate(_DoiAndUrl):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    abstract: str | None = Field(default=None, max_length=20000)
    venue: str | None = Field(default=None, max_length=300)
    year: int | None = Field(default=None, ge=MIN_YEAR, le=MAX_YEAR)
    pub_type: PublicationType | None = None
    authors: list[AuthorInput] | None = Field(default=None, min_length=1, max_length=100)
    project_ids: list[uuid.UUID] | None = None


class AuthorRead(BaseModel):
    user_id: uuid.UUID | None
    name: str
    author_order: int


class LinkedProject(BaseModel):
    id: uuid.UUID
    title: str


class PublicationRead(BaseModel):
    id: uuid.UUID
    title: str
    abstract: str | None
    venue: str | None
    year: int
    doi: str | None
    url: str | None
    pub_type: PublicationType
    created_by: uuid.UUID
    authors: list[AuthorRead]
    projects: list[LinkedProject]
    created_at: datetime
