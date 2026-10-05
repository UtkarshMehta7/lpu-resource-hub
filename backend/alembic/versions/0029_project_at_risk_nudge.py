"""a dean escalates a slipping project

Adds one `nudge_kind` enum value. Written by hand because autogenerate
compares tables, not enum members -- it sees nothing here and emits an empty
migration, the same omission that has bitten this repository before (0017,
0019, 0028).

No downgrade for the value: PostgreSQL cannot remove a member from an enum
type, and rewriting the type would mean rewriting every column that uses it.
A stale extra value is harmless; losing the rows is not.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # "This project is slipping -- please look at it." The only nudge that
    # travels downward, from an institutional reader to the people who can act.
    op.execute("ALTER TYPE nudge_kind ADD VALUE IF NOT EXISTS 'project_at_risk'")


def downgrade() -> None:
    # Deliberately nothing: see the module docstring.
    pass
