"""Index the columns scoped analytics filters on.

users.department_id and researcher_profiles.verification_status are both
filtered on every scoped aggregate (and by the coordinator verification
queue), but neither had an index.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-23 04:19:13.660292+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_researcher_profiles_verification_status"),
        "researcher_profiles",
        ["verification_status"],
        unique=False,
    )
    op.create_index(op.f("ix_users_department_id"), "users", ["department_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_department_id"), table_name="users")
    op.drop_index(
        op.f("ix_researcher_profiles_verification_status"), table_name="researcher_profiles"
    )
