"""Add research projects.

projects (with a generated weighted tsvector), project_skills,
project_research_areas and project_members. Status transitions are
enforced in app/modules/projects/service.py, not in the database.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-22 16:32:27.347763+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("objectives", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("department_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "pending_review", "active", "completed", "archived", name="project_status"
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "search_document",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
                "setweight(to_tsvector('english', coalesce(summary, '')), 'B') || "
                "setweight(to_tsvector('english', coalesce(description, '') || ' ' || "
                "coalesce(objectives, '')), 'C')",
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
            "start_date IS NULL OR end_date IS NULL OR start_date <= end_date",
            name=op.f("ck_projects_start_before_end"),
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_projects_department_id_departments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_projects_owner_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name=op.f("fk_projects_reviewed_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(op.f("ix_projects_department_id"), "projects", ["department_id"], unique=False)
    op.create_index(op.f("ix_projects_owner_id"), "projects", ["owner_id"], unique=False)
    op.create_index(
        "ix_projects_search_document",
        "projects",
        ["search_document"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(op.f("ix_projects_status"), "projects", ["status"], unique=False)
    op.create_table(
        "project_members",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("member_role", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_members_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_project_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_members")),
        sa.UniqueConstraint(
            "project_id", "user_id", name=op.f("uq_project_members_project_id_user_id")
        ),
    )
    op.create_index(
        op.f("ix_project_members_project_id"), "project_members", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_project_members_user_id"), "project_members", ["user_id"], unique=False
    )
    op.create_table(
        "project_research_areas",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("research_area_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_research_areas_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_area_id"],
            ["research_areas.id"],
            name=op.f("fk_project_research_areas_research_area_id_research_areas"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "project_id", "research_area_id", name=op.f("pk_project_research_areas")
        ),
    )
    op.create_table(
        "project_skills",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_skills_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("fk_project_skills_skill_id_skills"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id", "skill_id", name=op.f("pk_project_skills")),
    )


def downgrade() -> None:
    op.drop_table("project_skills")
    op.drop_table("project_research_areas")
    op.drop_index(op.f("ix_project_members_user_id"), table_name="project_members")
    op.drop_index(op.f("ix_project_members_project_id"), table_name="project_members")
    op.drop_table("project_members")
    op.drop_index(op.f("ix_projects_status"), table_name="projects")
    op.drop_index("ix_projects_search_document", table_name="projects", postgresql_using="gin")
    op.drop_index(op.f("ix_projects_owner_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_department_id"), table_name="projects")
    op.drop_table("projects")
    sa.Enum(name="project_status").drop(op.get_bind(), checkfirst=True)
