"""Add publications.

publications (generated weighted tsvector, sane-year CHECK, unique DOI),
publication_authors (a user OR an external name, ordered) and
project_publications.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-22 16:44:18.191702+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "publications",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("venue", sa.String(length=300), nullable=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column(
            "pub_type",
            sa.Enum(
                "journal_article",
                "conference_paper",
                "book_chapter",
                "book",
                "preprint",
                "thesis",
                "other",
                name="publication_type",
            ),
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "search_document",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
                "setweight(to_tsvector('english', coalesce(abstract, '')), 'B') || "
                "setweight(to_tsvector('english', coalesce(venue, '')), 'C')",
                persisted=True,
            ),
            nullable=True,
        ),
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
        sa.CheckConstraint(
            "year BETWEEN 1900 AND 2100", name=op.f("ck_publications_year_in_range")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_publications_created_by_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publications")),
        sa.UniqueConstraint("doi", name=op.f("uq_publications_doi")),
    )
    op.create_index(
        op.f("ix_publications_created_by"), "publications", ["created_by"], unique=False
    )
    op.create_index(
        "ix_publications_search_document",
        "publications",
        ["search_document"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(op.f("ix_publications_year"), "publications", ["year"], unique=False)
    op.create_table(
        "project_publications",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("publication_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_publications_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["publication_id"],
            ["publications.id"],
            name=op.f("fk_project_publications_publication_id_publications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "project_id", "publication_id", name=op.f("pk_project_publications")
        ),
    )
    op.create_table(
        "publication_authors",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("publication_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("external_name", sa.String(length=200), nullable=True),
        sa.Column("author_order", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "author_order >= 1", name=op.f("ck_publication_authors_author_order_positive")
        ),
        sa.CheckConstraint(
            "num_nonnulls(user_id, external_name) = 1",
            name=op.f("ck_publication_authors_exactly_one_author"),
        ),
        sa.ForeignKeyConstraint(
            ["publication_id"],
            ["publications.id"],
            name=op.f("fk_publication_authors_publication_id_publications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_publication_authors_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publication_authors")),
        sa.UniqueConstraint(
            "publication_id",
            "author_order",
            name=op.f("uq_publication_authors_publication_id_author_order"),
        ),
    )
    op.create_index(
        op.f("ix_publication_authors_publication_id"),
        "publication_authors",
        ["publication_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_publication_authors_user_id"), "publication_authors", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_publication_authors_user_id"), table_name="publication_authors")
    op.drop_index(op.f("ix_publication_authors_publication_id"), table_name="publication_authors")
    op.drop_table("publication_authors")
    op.drop_table("project_publications")
    op.drop_index(op.f("ix_publications_year"), table_name="publications")
    op.drop_index(
        "ix_publications_search_document", table_name="publications", postgresql_using="gin"
    )
    op.drop_index(op.f("ix_publications_created_by"), table_name="publications")
    op.drop_table("publications")
    sa.Enum(name="publication_type").drop(op.get_bind(), checkfirst=True)
