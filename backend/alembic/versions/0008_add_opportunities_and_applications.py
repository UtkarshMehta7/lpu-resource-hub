"""Add opportunities and applications.

opportunities (generated weighted tsvector, positions CHECK), opportunity_skills,
applications (one per applicant per opportunity) and application_events
(the applicant-visible status timeline).

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-22 16:59:50.990441+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "opportunity_type",
            sa.Enum(
                "research_assistant",
                "student_researcher",
                "project_assistant",
                "research_internship",
                "collaboration",
                name="opportunity_type",
            ),
            nullable=False,
        ),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("department_id", sa.UUID(), nullable=True),
        sa.Column("eligibility", sa.Text(), nullable=True),
        sa.Column("positions", sa.Integer(), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "open", "closed", "filled", name="opportunity_status"),
            server_default="draft",
            nullable=False,
        ),
        sa.Column(
            "search_document",
            postgresql.TSVECTOR(),
            sa.Computed(
                (
                    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
                    "setweight(to_tsvector('english', coalesce(description, '')), 'B') || "
                    "setweight(to_tsvector('english', coalesce(eligibility, '')), 'C')"
                ),
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
        sa.CheckConstraint("positions > 0", name=op.f("ck_opportunities_positions_positive")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_opportunities_created_by_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_opportunities_department_id_departments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_opportunities_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunities")),
    )
    op.create_index(
        op.f("ix_opportunities_created_by"), "opportunities", ["created_by"], unique=False
    )
    op.create_index(op.f("ix_opportunities_deadline"), "opportunities", ["deadline"], unique=False)
    op.create_index(
        op.f("ix_opportunities_department_id"), "opportunities", ["department_id"], unique=False
    )
    op.create_index(
        op.f("ix_opportunities_project_id"), "opportunities", ["project_id"], unique=False
    )
    op.create_index(
        "ix_opportunities_search_document",
        "opportunities",
        ["search_document"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(op.f("ix_opportunities_status"), "opportunities", ["status"], unique=False)
    op.create_table(
        "applications",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("opportunity_id", sa.UUID(), nullable=False),
        sa.Column("applicant_id", sa.UUID(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "submitted",
                "under_review",
                "shortlisted",
                "accepted",
                "rejected",
                "withdrawn",
                name="application_status",
            ),
            server_default="submitted",
            nullable=False,
        ),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["applicant_id"],
            ["users.id"],
            name=op.f("fk_applications_applicant_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name=op.f("fk_applications_decided_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_applications_opportunity_id_opportunities"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
        sa.UniqueConstraint(
            "opportunity_id",
            "applicant_id",
            name=op.f("uq_applications_opportunity_id_applicant_id"),
        ),
    )
    op.create_index(
        op.f("ix_applications_applicant_id"), "applications", ["applicant_id"], unique=False
    )
    op.create_index(
        op.f("ix_applications_opportunity_id"), "applications", ["opportunity_id"], unique=False
    )
    op.create_table(
        "opportunity_skills",
        sa.Column("opportunity_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column("is_required", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_opportunity_skills_opportunity_id_opportunities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("fk_opportunity_skills_skill_id_skills"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("opportunity_id", "skill_id", name=op.f("pk_opportunity_skills")),
    )
    op.create_table(
        "application_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "submitted",
                "under_review",
                "shortlisted",
                "accepted",
                "rejected",
                "withdrawn",
                name="application_status",
            ),
            nullable=False,
        ),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_application_events_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_application_events_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_events")),
    )
    op.create_index(
        op.f("ix_application_events_application_id"),
        "application_events",
        ["application_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_application_events_application_id"), table_name="application_events")
    op.drop_table("application_events")
    op.drop_table("opportunity_skills")
    op.drop_index(op.f("ix_applications_opportunity_id"), table_name="applications")
    op.drop_index(op.f("ix_applications_applicant_id"), table_name="applications")
    op.drop_table("applications")
    op.drop_index(op.f("ix_opportunities_status"), table_name="opportunities")
    op.drop_index(
        "ix_opportunities_search_document", table_name="opportunities", postgresql_using="gin"
    )
    op.drop_index(op.f("ix_opportunities_project_id"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_department_id"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_deadline"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_created_by"), table_name="opportunities")
    op.drop_table("opportunities")
    sa.Enum(name="application_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="opportunity_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="opportunity_type").drop(op.get_bind(), checkfirst=True)
