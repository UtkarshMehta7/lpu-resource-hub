"""A collaboration can be ended by either party.

One new value on the `collaboration_status` enum. Autogenerate does not see
enum members -- it compares tables -- so this is written by hand, the same way
0017 and 0019 added theirs.

The downgrade leaves the value in place: PostgreSQL cannot drop an enum value,
and rebuilding the type to remove it would rewrite every collaboration row for
no gain.

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-24 08:10:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE collaboration_status ADD VALUE IF NOT EXISTS 'ended'")


def downgrade() -> None:
    """Nothing to undo: see the module docstring."""
