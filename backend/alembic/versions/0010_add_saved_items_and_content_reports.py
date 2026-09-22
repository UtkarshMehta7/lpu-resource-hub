"""Add saved items and content reports.

saved_items (exactly one target, one bookmark per user per thing) and
content_reports (polymorphic target, one open report per reporter per thing).

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-22 17:38:02.349807+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_reports",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("reporter_id", sa.UUID(), nullable=False),
        sa.Column(
            "target_type",
            sa.Enum("project", "opportunity", "publication", "profile", name="report_target_type"),
            nullable=False,
        ),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.String(length=2000), nullable=False),
        sa.Column(
            "status",
            sa.Enum("open", "dismissed", "actioned", name="report_status"),
            server_default="open",
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["reporter_id"],
            ["users.id"],
            name=op.f("fk_content_reports_reporter_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name=op.f("fk_content_reports_reviewed_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_reports")),
    )
    op.create_index(
        op.f("ix_content_reports_reporter_id"), "content_reports", ["reporter_id"], unique=False
    )
    op.create_index(op.f("ix_content_reports_status"), "content_reports", ["status"], unique=False)
    op.create_index(
        op.f("ix_content_reports_target_id"), "content_reports", ["target_id"], unique=False
    )
    op.create_index(
        "uq_content_reports_open",
        "content_reports",
        ["reporter_id", "target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_table(
        "saved_items",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("opportunity_id", sa.UUID(), nullable=True),
        sa.Column("researcher_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "num_nonnulls(project_id, opportunity_id, researcher_id) = 1",
            name=op.f("ck_saved_items_exactly_one_target"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_saved_items_opportunity_id_opportunities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_saved_items_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["researcher_id"],
            ["users.id"],
            name=op.f("fk_saved_items_researcher_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_saved_items_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_items")),
    )
    op.create_index(op.f("ix_saved_items_user_id"), "saved_items", ["user_id"], unique=False)
    op.create_index(
        "uq_saved_items_opportunity",
        "saved_items",
        ["user_id", "opportunity_id"],
        unique=True,
        postgresql_where=sa.text("opportunity_id IS NOT NULL"),
    )
    op.create_index(
        "uq_saved_items_project",
        "saved_items",
        ["user_id", "project_id"],
        unique=True,
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )
    op.create_index(
        "uq_saved_items_researcher",
        "saved_items",
        ["user_id", "researcher_id"],
        unique=True,
        postgresql_where=sa.text("researcher_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_saved_items_researcher",
        table_name="saved_items",
        postgresql_where=sa.text("researcher_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_saved_items_project",
        table_name="saved_items",
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_saved_items_opportunity",
        table_name="saved_items",
        postgresql_where=sa.text("opportunity_id IS NOT NULL"),
    )
    op.drop_index(op.f("ix_saved_items_user_id"), table_name="saved_items")
    op.drop_table("saved_items")
    op.drop_index(
        "uq_content_reports_open",
        table_name="content_reports",
        postgresql_where=sa.text("status = 'open'"),
    )
    op.drop_index(op.f("ix_content_reports_target_id"), table_name="content_reports")
    op.drop_index(op.f("ix_content_reports_status"), table_name="content_reports")
    op.drop_index(op.f("ix_content_reports_reporter_id"), table_name="content_reports")
    op.drop_table("content_reports")
    sa.Enum(name="report_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="report_target_type").drop(op.get_bind(), checkfirst=True)
