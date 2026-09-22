"""Add entity embeddings (pgvector).

Enables the vector extension and stores one 384-dimension embedding per
(entity, model), with an HNSW cosine index for approximate nearest-neighbour
search. entity_id is deliberately not a foreign key: it points at five
different tables, and searches join back to the real table anyway.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-22 22:37:52.658439+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector must exist before a vector column can be created.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "entity_embeddings",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "entity_type",
            sa.Enum(
                "researcher",
                "project",
                "opportunity",
                "publication",
                "funding",
                name="embedding_entity_type",
            ),
            nullable=False,
        ),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entity_embeddings")),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            "model_name",
            name=op.f("uq_entity_embeddings_entity_type_entity_id_model_name"),
        ),
    )
    op.create_index(
        op.f("ix_entity_embeddings_entity_id"), "entity_embeddings", ["entity_id"], unique=False
    )
    op.create_index(
        op.f("ix_entity_embeddings_entity_type"), "entity_embeddings", ["entity_type"], unique=False
    )
    op.create_index(
        "ix_entity_embeddings_vector",
        "entity_embeddings",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    # pgvector must exist before a vector column can be created.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.drop_index(
        "ix_entity_embeddings_vector",
        table_name="entity_embeddings",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index(op.f("ix_entity_embeddings_entity_type"), table_name="entity_embeddings")
    op.drop_index(op.f("ix_entity_embeddings_entity_id"), table_name="entity_embeddings")
    op.drop_table("entity_embeddings")
    sa.Enum(name="embedding_entity_type").drop(op.get_bind(), checkfirst=True)
    # The vector extension is left installed: another migration may depend on it.
