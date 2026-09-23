"""Two-person admin promotion.

Making someone an administrator is the highest-impact action on the platform,
so it stops being a single click by a single person. An admin opens a
challenge; a six-digit code goes to the *target's* notification inbox; the
admin can only finish the promotion by entering the code the target gives
them. Possession of one admin session is no longer enough.

The code is stored only as a SHA-256 hash, expires, is single-use, and dies
after a few wrong guesses.

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-23 12:10:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The notification that carries the code to the target.
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'admin_promotion_code'")

    op.create_table(
        "admin_promotions",
        sa.Column(
            "id", sa.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("target_user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", sa.UUID(as_uuid=True), nullable=False),
        # SHA-256 of the six digits. The code itself is never stored.
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND attempts <= 10", name=op.f("ck_admin_promotions_attempts")
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["users.id"],
            name=op.f("fk_admin_promotions_target_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_admin_promotions_requested_by_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_promotions")),
    )
    # Looking up a target's live challenge is the hot path.
    op.create_index(
        op.f("ix_admin_promotions_target_user_id"),
        "admin_promotions",
        ["target_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_promotions_target_user_id"), table_name="admin_promotions")
    op.drop_table("admin_promotions")
    # PostgreSQL cannot drop a single enum value, and leaving it costs
    # nothing: rebuilding the type would mean rewriting the notifications
    # table for a label nothing references any more.
