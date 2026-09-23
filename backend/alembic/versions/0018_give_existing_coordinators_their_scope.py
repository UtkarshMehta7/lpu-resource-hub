"""Give existing coordinators the scope their department implies.

The service layer now keeps a coordinator's scope in step with their
department (admin/service.py::_sync_coordinator_scope), but that only fires
when the role or the department is next edited. Coordinators appointed
before that fix still sit with coordinator_scope_id NULL, which in practice
means an empty verification queue and 403 on every decision -- exactly the
bug that was reported, still present for the people it was reported about.

Data-only, and deliberately conservative: it fills in a scope only where
there is none, so a coordinator whose authority was set deliberately to
something other than their own department keeps it.

Irreversible in the honest sense -- downgrade does nothing, because we
cannot tell which NULLs we wrote from which were always there, and a
coordinator with no scope is a broken account, not a state worth restoring.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-24 02:30:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: Module-level so the test suite can run the statement this migration runs,
#: rather than a retyped copy of it that could drift.
BACKFILL_SQL = """
    UPDATE users
       SET coordinator_scope_type = 'department',
           coordinator_scope_id = department_id
     WHERE role = 'research_coordinator'
       AND department_id IS NOT NULL
       AND coordinator_scope_id IS NULL
"""


def upgrade() -> None:
    op.execute(sa.text(BACKFILL_SQL))


def downgrade() -> None:
    """Nothing to undo: see the module docstring."""
