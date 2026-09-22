"""Add funding calls, notifications, and saved funding items.

funding_opportunities (weighted tsvector, amount range CHECK) with its
research areas, notifications (with a partial unique dedupe key so a
reminder can never be sent twice), and saved_items.funding_id -- which also
widens the "exactly one target" CHECK from three columns to four.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-22 21:58:30.099317+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "funding_opportunities",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("eligibility", sa.Text(), nullable=True),
        sa.Column("amount_text", sa.String(length=200), nullable=True),
        sa.Column("amount_min", sa.Integer(), nullable=True),
        sa.Column("amount_max", sa.Integer(), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column("official_source_url", sa.String(length=2000), nullable=True),
        sa.Column(
            "status",
            sa.Enum("open", "closed", name="funding_status"),
            server_default="open",
            nullable=False,
        ),
        sa.Column("is_demo", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "search_document",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
                "setweight(to_tsvector('english', coalesce(organization, '')), 'B') || "
                "setweight(to_tsvector('english', coalesce(description, '')), 'C') || "
                "setweight(to_tsvector('english', coalesce(eligibility, '')), 'D')",
                persisted=True,
            ),
            nullable=True,
        ),
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
            "amount_min IS NULL OR amount_max IS NULL OR amount_min <= amount_max",
            name=op.f("ck_funding_opportunities_amount_range_ordered"),
        ),
        sa.CheckConstraint(
            "amount_min IS NULL OR amount_min >= 0",
            name=op.f("ck_funding_opportunities_amount_min_not_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_funding_opportunities_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_funding_opportunities")),
    )
    op.create_index(
        op.f("ix_funding_opportunities_deadline"),
        "funding_opportunities",
        ["deadline"],
        unique=False,
    )
    op.create_index(
        op.f("ix_funding_opportunities_status"), "funding_opportunities", ["status"], unique=False
    )
    op.create_index(
        "ix_funding_search_document",
        "funding_opportunities",
        ["search_document"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "notification_type",
            sa.Enum(
                "application_received",
                "application_decided",
                "collaboration_request",
                "collaboration_response",
                "booking_decided",
                "project_reviewed",
                "profile_verified",
                "relevant_opportunity",
                "deadline_reminder",
                name="notification_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("dedupe_key", sa.String(length=200), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)
    op.create_index(
        "ix_notifications_user_unread", "notifications", ["user_id", "read_at"], unique=False
    )
    op.create_index(
        "uq_notifications_dedupe_key",
        "notifications",
        ["user_id", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )
    op.create_table(
        "funding_research_areas",
        sa.Column("funding_id", sa.UUID(), nullable=False),
        sa.Column("research_area_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["funding_id"],
            ["funding_opportunities.id"],
            name=op.f("fk_funding_research_areas_funding_id_funding_opportunities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_area_id"],
            ["research_areas.id"],
            name=op.f("fk_funding_research_areas_research_area_id_research_areas"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "funding_id", "research_area_id", name=op.f("pk_funding_research_areas")
        ),
    )
    op.add_column("saved_items", sa.Column("funding_id", sa.UUID(), nullable=True))
    # A saved item still points at exactly one thing -- now out of four.
    op.drop_constraint(op.f("ck_saved_items_exactly_one_target"), "saved_items", type_="check")
    op.create_check_constraint(
        "exactly_one_target",
        "saved_items",
        "num_nonnulls(project_id, opportunity_id, researcher_id, funding_id) = 1",
    )
    op.create_index(
        "uq_saved_items_funding",
        "saved_items",
        ["user_id", "funding_id"],
        unique=True,
        postgresql_where=sa.text("funding_id IS NOT NULL"),
    )
    op.create_foreign_key(
        op.f("fk_saved_items_funding_id_funding_opportunities"),
        "saved_items",
        "funding_opportunities",
        ["funding_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_saved_items_funding_id_funding_opportunities"), "saved_items", type_="foreignkey"
    )
    op.drop_index(
        "uq_saved_items_funding",
        table_name="saved_items",
        postgresql_where=sa.text("funding_id IS NOT NULL"),
    )
    op.drop_constraint(op.f("ck_saved_items_exactly_one_target"), "saved_items", type_="check")
    op.drop_column("saved_items", "funding_id")
    op.create_check_constraint(
        "exactly_one_target",
        "saved_items",
        "num_nonnulls(project_id, opportunity_id, researcher_id) = 1",
    )
    op.drop_table("funding_research_areas")
    op.drop_index(
        "uq_notifications_dedupe_key",
        table_name="notifications",
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(
        "ix_funding_search_document", table_name="funding_opportunities", postgresql_using="gin"
    )
    op.drop_index(op.f("ix_funding_opportunities_status"), table_name="funding_opportunities")
    op.drop_index(op.f("ix_funding_opportunities_deadline"), table_name="funding_opportunities")
    op.drop_table("funding_opportunities")
    sa.Enum(name="notification_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="funding_status").drop(op.get_bind(), checkfirst=True)
