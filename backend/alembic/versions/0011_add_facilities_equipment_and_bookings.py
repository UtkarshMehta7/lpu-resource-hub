"""Add facilities, equipment and bookings.

Enables btree_gist so the bookings EXCLUDE constraint can combine a uuid
equality operator with a tstzrange overlap operator: two APPROVED bookings
of the same equipment can never overlap, enforced by PostgreSQL itself.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-22 21:34:13.950672+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The EXCLUDE constraint below mixes = (uuid) with && (range), which
    # plain GiST can't index without btree_gist.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "facilities",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("department_id", sa.UUID(), nullable=True),
        sa.Column("location", sa.String(length=300), nullable=True),
        sa.Column("contact", sa.String(length=300), nullable=True),
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
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_facilities_department_id_departments"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_facilities")),
        sa.UniqueConstraint("department_id", "name", name=op.f("uq_facilities_department_id_name")),
    )
    op.create_index(
        op.f("ix_facilities_department_id"), "facilities", ["department_id"], unique=False
    )
    op.create_table(
        "equipment",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("facility_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=150), nullable=True),
        sa.Column(
            "maintenance_status",
            sa.Enum("available", "maintenance", "retired", name="maintenance_status"),
            server_default="available",
            nullable=False,
        ),
        sa.Column("students_allowed", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("requires_approval", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("max_hours", sa.Integer(), server_default="8", nullable=False),
        sa.Column("min_lead_hours", sa.Integer(), server_default="0", nullable=False),
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
        sa.CheckConstraint("max_hours > 0", name=op.f("ck_equipment_max_hours_positive")),
        sa.CheckConstraint(
            "min_lead_hours >= 0", name=op.f("ck_equipment_min_lead_hours_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name=op.f("fk_equipment_facility_id_facilities"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment")),
    )
    op.create_index(op.f("ix_equipment_category"), "equipment", ["category"], unique=False)
    op.create_index(op.f("ix_equipment_facility_id"), "equipment", ["facility_id"], unique=False)
    op.create_table(
        "bookings",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("equipment_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("period", postgresql.TSTZRANGE(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "approved", "rejected", "cancelled", "completed", name="booking_status"
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
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
        postgresql.ExcludeConstraint(
            (sa.column("equipment_id"), "="),
            (sa.column("period"), "&&"),
            where=sa.text("status = 'approved'"),
            using="gist",
            name="no_overlapping_approved_bookings",
        ),
        sa.CheckConstraint(
            "lower(period) < upper(period)", name=op.f("ck_bookings_period_not_empty")
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name=op.f("fk_bookings_decided_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["equipment.id"],
            name=op.f("fk_bookings_equipment_id_equipment"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_bookings_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bookings")),
    )
    op.create_index(op.f("ix_bookings_equipment_id"), "bookings", ["equipment_id"], unique=False)
    op.create_index(op.f("ix_bookings_status"), "bookings", ["status"], unique=False)
    op.create_index(op.f("ix_bookings_user_id"), "bookings", ["user_id"], unique=False)


def downgrade() -> None:
    # The EXCLUDE constraint below mixes = (uuid) with && (range), which
    # plain GiST can't index without btree_gist.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.drop_index(op.f("ix_bookings_user_id"), table_name="bookings")
    op.drop_index(op.f("ix_bookings_status"), table_name="bookings")
    op.drop_index(op.f("ix_bookings_equipment_id"), table_name="bookings")
    op.drop_table("bookings")
    op.drop_index(op.f("ix_equipment_facility_id"), table_name="equipment")
    op.drop_index(op.f("ix_equipment_category"), table_name="equipment")
    op.drop_table("equipment")
    op.drop_index(op.f("ix_facilities_department_id"), table_name="facilities")
    op.drop_table("facilities")
    sa.Enum(name="booking_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="maintenance_status").drop(op.get_bind(), checkfirst=True)
    # btree_gist is left installed: dropping an extension another migration
    # might later depend on is riskier than leaving it in place.
