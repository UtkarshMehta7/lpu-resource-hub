"""Add organisation, taxonomy and profiles.

Schools/departments (admin-managed org structure), the shared skill/
research-area taxonomy with aliases and suggestions, student/researcher
profiles, and the user_skills/user_research_areas join tables. Adds
users.department_id (nullable FK), users.is_demo (seed-script marker) and
users.onboarding_complete (recomputed by app/modules/profiles/service.py).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-22 09:34:51.740554+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_areas",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["research_areas.id"],
            name=op.f("fk_research_areas_parent_id_research_areas"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_areas")),
    )
    op.create_index(op.f("ix_research_areas_name"), "research_areas", ["name"], unique=False)
    op.create_table(
        "schools",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schools")),
        sa.UniqueConstraint("name", name=op.f("uq_schools_name")),
    )
    op.create_table(
        "skills",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skills")),
    )
    op.create_index(op.f("ix_skills_name"), "skills", ["name"], unique=True)
    op.create_table(
        "departments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("school_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
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
            ["school_id"],
            ["schools.id"],
            name=op.f("fk_departments_school_id_schools"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_departments")),
        sa.UniqueConstraint("school_id", "name", name=op.f("uq_departments_school_id_name")),
    )
    op.create_index(op.f("ix_departments_school_id"), "departments", ["school_id"], unique=False)
    op.create_table(
        "tag_aliases",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("alias", sa.String(length=150), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=True),
        sa.Column("research_area_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "num_nonnulls(skill_id, research_area_id) = 1",
            name=op.f("ck_tag_aliases_ck_exactly_one_target"),
        ),
        sa.ForeignKeyConstraint(
            ["research_area_id"],
            ["research_areas.id"],
            name=op.f("fk_tag_aliases_research_area_id_research_areas"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("fk_tag_aliases_skill_id_skills"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tag_aliases")),
    )
    op.create_index(op.f("ix_tag_aliases_alias"), "tag_aliases", ["alias"], unique=True)
    op.create_table(
        "researcher_profiles",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("designation", sa.String(length=150), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column(
            "availability",
            sa.Enum("available", "limited", "unavailable", name="researcher_availability"),
            server_default="available",
            nullable=False,
        ),
        sa.Column("links", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "verification_status",
            sa.Enum("unverified", "pending", "verified", "rejected", name="verification_status"),
            server_default="unverified",
            nullable=False,
        ),
        sa.Column("verified_by", sa.UUID(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_researcher_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"],
            ["users.id"],
            name=op.f("fk_researcher_profiles_verified_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_researcher_profiles")),
    )
    op.create_table(
        "student_profiles",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("program", sa.String(length=150), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("interests", sa.Text(), nullable=True),
        sa.Column("is_discoverable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_student_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_student_profiles")),
    )
    op.create_table(
        "tag_suggestions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("suggested_name", sa.String(length=150), nullable=False),
        sa.Column(
            "suggested_type",
            sa.Enum("skill", "research_area", name="tag_suggestion_type"),
            nullable=False,
        ),
        sa.Column("suggested_by", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", name="tag_suggestion_status"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name=op.f("fk_tag_suggestions_reviewed_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["suggested_by"],
            ["users.id"],
            name=op.f("fk_tag_suggestions_suggested_by_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tag_suggestions")),
    )
    op.create_table(
        "user_research_areas",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("research_area_id", sa.UUID(), nullable=False),
        sa.Column("is_expertise", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(
            ["research_area_id"],
            ["research_areas.id"],
            name=op.f("fk_user_research_areas_research_area_id_research_areas"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_research_areas_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "research_area_id", name=op.f("pk_user_research_areas")),
    )
    op.create_table(
        "user_skills",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column("proficiency", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint(
            "proficiency BETWEEN 1 AND 5", name=op.f("ck_user_skills_ck_proficiency_range")
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("fk_user_skills_skill_id_skills"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_skills_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "skill_id", name=op.f("pk_user_skills")),
    )
    op.add_column("users", sa.Column("department_id", sa.UUID(), nullable=True))
    op.add_column(
        "users", sa.Column("is_demo", sa.Boolean(), server_default=sa.text("false"), nullable=False)
    )
    op.add_column(
        "users",
        sa.Column(
            "onboarding_complete", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.create_foreign_key(
        op.f("fk_users_department_id_departments"),
        "users",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_users_department_id_departments"), "users", type_="foreignkey")
    op.drop_column("users", "onboarding_complete")
    op.drop_column("users", "is_demo")
    op.drop_column("users", "department_id")
    op.drop_table("user_skills")
    op.drop_table("user_research_areas")
    op.drop_table("tag_suggestions")
    op.drop_table("student_profiles")
    op.drop_table("researcher_profiles")
    op.drop_index(op.f("ix_tag_aliases_alias"), table_name="tag_aliases")
    op.drop_table("tag_aliases")
    op.drop_index(op.f("ix_departments_school_id"), table_name="departments")
    op.drop_table("departments")
    op.drop_index(op.f("ix_skills_name"), table_name="skills")
    op.drop_table("skills")
    op.drop_table("schools")
    op.drop_index(op.f("ix_research_areas_name"), table_name="research_areas")
    op.drop_table("research_areas")
