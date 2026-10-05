"""files shared in a conversation

Adds `message_attachments`, which holds the bytes itself rather than pointing
at a shared blob table. The FK to `messages` cascades, so a deleted message,
conversation, project or person takes the bytes with it -- no orphan rows
accumulating against a 0.5 GB database quota, and no second lifecycle to
remember.

Purely additive, so the boot-time migration can apply it unattended
(ADR 0024).

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_attachments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=200), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_message_attachments_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_attachments")),
    )
    op.create_index(
        op.f("ix_message_attachments_message_id"),
        "message_attachments",
        ["message_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_message_attachments_message_id"), table_name="message_attachments")
    op.drop_table("message_attachments")
