"""an institution-wide role belongs to no department

A fix to the service layer does not fix the rows already in the deployed
database -- the same lesson migration 0018 recorded for coordinator scope.
`_sync_institution_wide_placement` now clears the department whenever a
person becomes a dean or an administrator, but the dean already on the
deployed instance was sitting in one, placed from the users page before the
rule existed.

Deans and administrators only. Nothing else is touched, and a person who
genuinely belongs to a department keeps it.

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET department_id = NULL
        WHERE role IN ('admin', 'dean_of_research')
          AND department_id IS NOT NULL
        """
    )


def downgrade() -> None:
    # Which department each of them used to sit in is exactly the information
    # this migration exists to discard, so it cannot be put back. Reversing it
    # would mean inventing placements.
    pass
