"""Stored embeddings for searchable entities."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.ml.embeddings import EMBEDDING_DIM


class EntityType(StrEnum):
    RESEARCHER = "researcher"
    PROJECT = "project"
    OPPORTUNITY = "opportunity"
    PUBLICATION = "publication"
    FUNDING = "funding"


class EntityEmbedding(Base):
    """One vector per (entity, model).

    `entity_id` has no foreign key on purpose: it points at five different
    tables, and a stale row is harmless -- searches join back to the real
    table, so an embedding whose entity is gone simply never matches.
    """

    __tablename__ = "entity_embeddings"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "model_name"),
        Index(
            "ix_entity_embeddings_vector",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    entity_type: Mapped[EntityType] = mapped_column(
        Enum(
            EntityType,
            name="embedding_entity_type",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # What the vector was built from: unchanged hash means no re-embedding.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
