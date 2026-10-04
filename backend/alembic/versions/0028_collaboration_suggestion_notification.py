"""collaboration suggestion notification

Adds one `notification_type` enum value. Written by hand because autogenerate
compares tables, not enum members -- it sees nothing here and emits an empty
migration, which is how the same omission has bitten this repository before
(0017, 0019).

There is no downgrade for the value itself: PostgreSQL cannot remove a member
from an enum type, and rewriting the type would mean rewriting every column
that uses it. A stale extra value is harmless; losing the rows is not.

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # "You two work on similar things and have never published together."
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'collaboration_suggestion'")


def downgrade() -> None:
    # Deliberately nothing: see the module docstring. Removing an enum member
    # is not something PostgreSQL offers, and the rows that use it matter more
    # than the tidiness of the type.
    pass
