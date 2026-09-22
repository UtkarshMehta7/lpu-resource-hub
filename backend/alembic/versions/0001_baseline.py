"""Baseline: empty starting point for the migration history.

Creates no tables. Running ``alembic upgrade head`` against an empty database
creates only Alembic's own ``alembic_version`` table, proving the migration
pipeline works end to end. Domain tables arrive with the steps that need them.

Revision ID: 0001
Revises:
Create Date: 2026-09-22 00:00:00+00:00
"""

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
