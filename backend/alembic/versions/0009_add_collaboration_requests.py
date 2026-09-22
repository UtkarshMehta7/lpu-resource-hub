"""Add collaboration requests.

collaboration_requests with a no-self CHECK and a partial unique index
(NULLS NOT DISTINCT) allowing one PENDING request per sender/recipient/project.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-22 17:11:03.074003+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collaboration_requests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("sender_id", sa.UUID(), nullable=False),
        sa.Column("recipient_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "accepted", "declined", "cancelled", name="collaboration_status"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sender_id <> recipient_id", name=op.f("ck_collaboration_requests_not_self")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_collaboration_requests_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["users.id"],
            name=op.f("fk_collaboration_requests_recipient_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"],
            ["users.id"],
            name=op.f("fk_collaboration_requests_sender_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collaboration_requests")),
    )
    op.create_index(
        op.f("ix_collaboration_requests_recipient_id"),
        "collaboration_requests",
        ["recipient_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collaboration_requests_sender_id"),
        "collaboration_requests",
        ["sender_id"],
        unique=False,
    )
    op.create_index(
        "uq_collaboration_requests_pending",
        "collaboration_requests",
        ["sender_id", "recipient_id", "project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_collaboration_requests_pending",
        table_name="collaboration_requests",
        postgresql_where=sa.text("status = 'pending'"),
        postgresql_nulls_not_distinct=True,
    )
    op.drop_index(op.f("ix_collaboration_requests_sender_id"), table_name="collaboration_requests")
    op.drop_index(
        op.f("ix_collaboration_requests_recipient_id"), table_name="collaboration_requests"
    )
    op.drop_table("collaboration_requests")
    sa.Enum(name="collaboration_status").drop(op.get_bind(), checkfirst=True)
