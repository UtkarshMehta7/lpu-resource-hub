"""Record who provisioned each account.

Accounts are no longer self-registered: every one is created by someone a
rung above in the institutional hierarchy (admin -> coordinator -> faculty
-> student). users.created_by records that chain, so the database can answer
"who let this person in" for audit without a second table.

Nullable, because the bootstrap admin (scripts/create_admin.py) has no
creator, and because accounts that predate this migration have no way to
know theirs.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-23 11:05:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("created_by", sa.UUID(as_uuid=True), nullable=True))
    # SET NULL, not CASCADE: removing a coordinator must never remove the
    # faculty they provisioned.
    op.create_foreign_key(
        op.f("fk_users_created_by_users"),
        "users",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_users_created_by"), "users", ["created_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_created_by"), table_name="users")
    op.drop_constraint(op.f("fk_users_created_by_users"), "users", type_="foreignkey")
    op.drop_column("users", "created_by")
