"""Conversation threads, scoped to an accepted request or a project team.

Three tables. `conversations` carries two nullable foreign keys with a CHECK
that exactly one is set, rather than one polymorphic subject id: they are real
foreign keys, so deleting a project or a request takes its thread with it. A
polymorphic id cannot cascade and would strand threads forever. The same shape
as `tag_aliases` (migration 0004), for the same reason.

`conversation_participants` holds membership and how far each person has read,
so leaving a project revokes access without touching the messages. `messages`
can be hidden by a moderator (hidden_at/hidden_by) but never deleted, so a
thread does not develop holes.

sender_id cascades, like every other content table: deleting an account takes
its messages with it, which `DeletionImpact` now counts so the confirmation
says so (ADR 0021, ADR 0022).

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-24 04:22:27.671197+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Two existing enums gain a value. Autogenerate never sees these -- it
    # compares tables, not enum members -- so they are written by hand, the
    # same way migration 0017 added admin_promotion_code.
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'message_received'")
    op.execute("ALTER TYPE report_target_type ADD VALUE IF NOT EXISTS 'message'")

    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("collaboration_request_id", sa.UUID(), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
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
            "(collaboration_request_id IS NULL) <> (project_id IS NULL)",
            name=op.f("ck_conversations_exactly_one_subject"),
        ),
        sa.ForeignKeyConstraint(
            ["collaboration_request_id"],
            ["collaboration_requests.id"],
            name=op.f("fk_conversations_collaboration_request_id_collaboration_requests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_conversations_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
        sa.UniqueConstraint("collaboration_request_id", name="uq_conversations_collaboration"),
        sa.UniqueConstraint("project_id", name="uq_conversations_project"),
    )
    op.create_table(
        "conversation_participants",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("muted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_conversation_participants_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_conversation_participants_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "conversation_id", "user_id", name=op.f("pk_conversation_participants")
        ),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("sender_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hidden_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_messages_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["hidden_by"],
            ["users.id"],
            name=op.f("fk_messages_hidden_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"],
            ["users.id"],
            name=op.f("fk_messages_sender_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(op.f("ix_messages_sender_id"), "messages", ["sender_id"], unique=False)
    op.create_index(
        "ix_messages_thread_order",
        "messages",
        ["conversation_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    # The two enum values stay. PostgreSQL cannot drop one, and recreating
    # both types to remove them would rewrite every notification and report
    # row -- far more destructive than leaving two unused labels behind.
    op.drop_index("ix_messages_thread_order", table_name="messages")
    op.drop_index(op.f("ix_messages_sender_id"), table_name="messages")
    op.drop_table("messages")
    op.drop_table("conversation_participants")
    op.drop_table("conversations")
