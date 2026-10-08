"""An invention can be FILED WITH the university, not only recorded after

ADR 0035 modelled the patent lifecycle as "what the office did". That was the
second half. The half that decides whether a patent ever exists happens here:
an inventor discloses, the IP cell assesses, the university decides to file or
not. Four stages are added in front of FILED, and `filing_date` becomes
nullable, because nothing inside the university has one yet.

**Autogenerate wrote none of the important parts.** It compares tables, not
enum members, so the four new `patent_status` values are added by hand (the
same gotcha as migrations 0017 and 0019), and it does not emit CHECK
constraints either.

Safe on existing rows: every patent recorded before this is FILED or later and
already carries a filing date, which is exactly what the new CHECK requires.

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-08 09:56:29.910098+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate never sees enum members. IF NOT EXISTS so a re-run is
    # harmless; the values are not USED until a later statement, which is what
    # lets this run inside Alembic's transaction.
    for value in ("disclosed", "under_assessment", "approved_to_file", "declined"):
        op.execute(f"ALTER TYPE patent_status ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column("patents", sa.Column("reference", sa.String(length=32), nullable=True))
    op.add_column("patents", sa.Column("problem_statement", sa.Text(), nullable=True))
    op.add_column("patents", sa.Column("novelty", sa.Text(), nullable=True))
    op.add_column("patents", sa.Column("known_prior_art", sa.Text(), nullable=True))
    op.add_column("patents", sa.Column("public_disclosure_date", sa.Date(), nullable=True))
    op.add_column("patents", sa.Column("public_disclosure_note", sa.Text(), nullable=True))
    op.add_column("patents", sa.Column("funding_source", sa.String(length=300), nullable=True))
    op.add_column("patents", sa.Column("commercial_potential", sa.Text(), nullable=True))
    op.add_column("patents", sa.Column("assessment_note", sa.Text(), nullable=True))
    op.add_column("patents", sa.Column("assessed_by", sa.UUID(), nullable=True))
    op.add_column("patents", sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("patents", "filing_date", existing_type=sa.DATE(), nullable=True)
    op.create_unique_constraint(op.f("uq_patents_reference"), "patents", ["reference"])
    op.create_foreign_key(
        op.f("fk_patents_assessed_by_users"),
        "patents",
        "users",
        ["assessed_by"],
        ["id"],
        ondelete="SET NULL",
    )

    # Autogenerate does not emit CHECK constraints either. Nothing inside the
    # university has a filing date; nothing at the office lacks one.
    op.create_check_constraint(
        "filing_date_exactly_when_filed",
        "patents",
        # Cast to text on purpose: Postgres refuses an enum LITERAL whose
        # value was added by the ALTER TYPE above and not yet committed
        # ("new enum values must be committed before they can be used").
        # Comparing text to text needs no such literal, so the whole pipeline
        # still lands in one migration instead of two.
        "(status::text IN ('disclosed', 'under_assessment', 'approved_to_file', "
        "'declined')) = (filing_date IS NULL)",
    )
    # "No" without a reason is what stops the next person disclosing.
    op.create_check_constraint(
        "declining_gives_a_reason",
        "patents",
        "status::text <> 'declined' OR assessment_note IS NOT NULL",
    )


def downgrade() -> None:
    # The four added enum values stay: PostgreSQL cannot drop one, and
    # recreating the type would mean rewriting every row that uses it. A
    # downgrade therefore leaves a wider enum than it found, which is
    # harmless -- the CHECK and the application both refuse the extra values.
    # Bare names: the metadata naming convention adds the ck_patents_ prefix,
    # and passing the full name here produces ck_patents_ck_patents_...
    op.drop_constraint("declining_gives_a_reason", "patents", type_="check")
    op.drop_constraint("filing_date_exactly_when_filed", "patents", type_="check")
    op.drop_constraint(op.f("fk_patents_assessed_by_users"), "patents", type_="foreignkey")
    op.drop_constraint(op.f("uq_patents_reference"), "patents", type_="unique")
    op.alter_column("patents", "filing_date", existing_type=sa.DATE(), nullable=False)
    op.drop_column("patents", "assessed_at")
    op.drop_column("patents", "assessed_by")
    op.drop_column("patents", "assessment_note")
    op.drop_column("patents", "commercial_potential")
    op.drop_column("patents", "funding_source")
    op.drop_column("patents", "public_disclosure_note")
    op.drop_column("patents", "public_disclosure_date")
    op.drop_column("patents", "known_prior_art")
    op.drop_column("patents", "novelty")
    op.drop_column("patents", "problem_statement")
    op.drop_column("patents", "reference")
    # ### end Alembic commands ###
