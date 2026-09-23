"""Log in with the LPU registration number.

Adds users.registration_number (the UMS-style identifier people log in with),
makes users.email optional (contact information, not a credential), and adds
must_change_password for accounts created with a temporary password.

Existing rows are backfilled with obviously fake DEMO000001-style numbers: a
demo row must never look like a real LPU registration number.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-23 03:40:21.908543+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("registration_number", sa.String(length=50), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    # Backfill before the NOT NULL: existing accounts have no number yet.
    op.execute(
        """
        UPDATE users AS u
        SET registration_number = numbered.value
        FROM (
            SELECT id,
                   'DEMO' || lpad((row_number() OVER (ORDER BY created_at, id))::text, 6, '0')
                       AS value
            FROM users
        ) AS numbered
        WHERE u.id = numbered.id
        """
    )
    op.alter_column("users", "registration_number", nullable=False)
    op.create_index(
        op.f("ix_users_registration_number"), "users", ["registration_number"], unique=True
    )
    # Email is no longer a credential, so it may be absent.
    op.alter_column("users", "email", existing_type=sa.VARCHAR(length=320), nullable=True)


def downgrade() -> None:
    # Email becomes required again, so give rows that lack one a unique
    # placeholder rather than failing the migration.
    op.execute(
        """
        UPDATE users
        SET email = lower(registration_number) || '@placeholder.invalid'
        WHERE email IS NULL
        """
    )
    op.alter_column("users", "email", existing_type=sa.VARCHAR(length=320), nullable=False)
    op.drop_index(op.f("ix_users_registration_number"), table_name="users")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "registration_number")
