"""A record of every profile import.

An import writes to a researcher's own profile and to the publication
register, so it is a sensitive action and leaves a row behind: what was
pulled, from where, how much of it was already known, and what the researcher
chose to accept. Without this there is no way to answer "where did this
publication come from" six months later.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProfileImport(Base):
    __tablename__ = "profile_imports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    orcid_id: Mapped[str | None] = mapped_column(String(19), nullable=True)
    # Which connectors actually answered, and which failed and why. Shape:
    # {"used": ["orcid", "openalex"], "failed": {"semantic_scholar": "..."}}
    sources: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    # Which profile fields the researcher accepted, e.g. ["bio", "links"].
    applied_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    works_found: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    works_imported: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    works_already_known: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["ProfileImport"]
