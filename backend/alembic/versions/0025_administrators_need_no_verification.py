"""administrators need no verification

A data fix, not a schema change.

Verification means somebody senior vouched for a researcher's record. Nobody
is senior to an administrator, so an administrator sitting at PENDING was
asking a coordinator to vouch for their own senior -- and the queue had no
role filter, so they really did appear there.

The code now verifies an administrator the moment they save a profile and
excludes them from the queue either way. This brings existing rows into line,
so a deployed database heals itself on the next boot rather than waiting for
each administrator to re-save.

Deliberately not reversible in the other direction: downgrading cannot know
which administrators were PENDING beforehand, and putting them back would
recreate the bug.

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-29 06:11:20.142457+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE researcher_profiles
           SET verification_status = 'verified',
               verified_at = COALESCE(verified_at, now())
         WHERE verification_status <> 'verified'
           AND user_id IN (SELECT id FROM users WHERE role = 'admin')
        """
    )


def downgrade() -> None:
    # Nothing to undo: which administrators were previously PENDING is not
    # recorded, and restoring it would put them back in a queue no one should
    # be able to act on.
    pass
