"""Add full-text search to the researcher directory.

Enables pg_trgm, adds the weighted `search_document` tsvector on
researcher_profiles with a GIN index, and a trigram GIN index on
users.full_name so misspelled name searches still match. Backfills every
existing researcher profile with the same statement
app/modules/profiles/service.py uses to keep it fresh.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-22 13:10:24.285074+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BACKFILL_SEARCH_DOCUMENTS = """
    UPDATE researcher_profiles AS rp
    SET search_document =
           setweight(to_tsvector('english', coalesce(u.full_name, '')), 'A')
        || setweight(to_tsvector('english',
               coalesce(rp.designation, '') || ' '
            || coalesce((SELECT string_agg(s.name, ' ')
                           FROM user_skills us
                           JOIN skills s ON s.id = us.skill_id
                          WHERE us.user_id = rp.user_id), '') || ' '
            || coalesce((SELECT string_agg(ra.name, ' ')
                           FROM user_research_areas ura
                           JOIN research_areas ra ON ra.id = ura.research_area_id
                          WHERE ura.user_id = rp.user_id), '')
           ), 'B')
        || setweight(to_tsvector('english', coalesce(rp.bio, '')), 'C')
    FROM users u
    WHERE u.id = rp.user_id
"""


def upgrade() -> None:
    # The trigram index below cannot be created without this.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.add_column(
        "researcher_profiles",
        sa.Column("search_document", postgresql.TSVECTOR(), nullable=True),
    )
    op.create_index(
        "ix_researcher_profiles_search_document",
        "researcher_profiles",
        ["search_document"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_users_full_name_trgm",
        "users",
        ["full_name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"full_name": "gin_trgm_ops"},
    )
    op.execute(BACKFILL_SEARCH_DOCUMENTS)


def downgrade() -> None:
    op.drop_index(
        "ix_users_full_name_trgm",
        table_name="users",
        postgresql_using="gin",
        postgresql_ops={"full_name": "gin_trgm_ops"},
    )
    op.drop_index(
        "ix_researcher_profiles_search_document",
        table_name="researcher_profiles",
        postgresql_using="gin",
    )
    op.drop_column("researcher_profiles", "search_document")
    # pg_trgm is left installed: other steps (and other databases on the same
    # cluster) may rely on it.
