"""Add coordinator scope and audit log.

Adds `users.coordinator_scope_type`/`coordinator_scope_id` (no FK on the id:
it is a polymorphic reference resolved by scope_type, and the referenced
tables -- departments etc. -- don't exist until Step 3) and the append-only
`audit_logs` table. See app/modules/admin/service.py and
app/modules/audit/service.py.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-22 09:14:26.085840+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_logs_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"], unique=False)
    op.create_index(op.f("ix_audit_logs_entity_id"), "audit_logs", ["entity_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_entity_type"), "audit_logs", ["entity_type"], unique=False)

    # op.add_column() with a standalone Enum does not create the Postgres
    # type itself (unlike create_table, which does via SQLAlchemy's DDL
    # events) -- create it explicitly first.
    coordinator_scope_type_enum = sa.Enum(
        "department", "school", "university", name="coordinator_scope_type"
    )
    coordinator_scope_type_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users",
        sa.Column("coordinator_scope_type", coordinator_scope_type_enum, nullable=True),
    )
    op.add_column("users", sa.Column("coordinator_scope_id", sa.UUID(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "coordinator_scope_id")
    op.drop_column("users", "coordinator_scope_type")
    sa.Enum(name="coordinator_scope_type").drop(op.get_bind(), checkfirst=True)
    op.drop_index(op.f("ix_audit_logs_entity_type"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_entity_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
    op.drop_table("audit_logs")
