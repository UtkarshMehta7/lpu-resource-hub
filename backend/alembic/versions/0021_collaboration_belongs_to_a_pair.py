"""A collaboration belongs to a pair of people, not to a request.

Keying the relationship and its conversation to a *request* produced three
bugs at once: you could request somebody you already collaborated with,
accepting that opened a second conversation so the pair's history split in
two, and A->B and B->A were separate rows so two people could hold pending
requests to each other. Modelling the pair fixes all three (ADR 0023).

The data work is the risky half, and it is deliberately conservative:

* every existing request is mapped to a pair, ordered so {a,b} and {b,a} are
  one row, and the pair's state is taken from the strongest request it has --
  accepted beats ended beats pending beats nothing;
* where a pair ended up with more than one conversation, the oldest is kept
  and every message is repointed to it. **No message is deleted.**
* merging read marks takes the EARLIEST of the two, and NULL (never opened)
  wins over any timestamp. Merging must not mark something read that nobody
  has seen: showing an item unread twice is a nuisance, hiding it is a
  failure.

Irreversible by design. The downgrade drops what this added but cannot unpick
a merge -- once two threads are one, which message came from which is no
longer a question the data can answer.

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-24 09:30:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Created explicitly, then referenced with create_type=False: create_table
    # would otherwise try to create the type a second time and fail.
    state = postgresql.ENUM(
        "none", "requested", "active", "ended", name="collaboration_state", create_type=False
    )
    sa.Enum("none", "requested", "active", "ended", name="collaboration_state").create(
        op.get_bind(), checkfirst=True
    )

    op.create_table(
        "collaborations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_a_id", sa.UUID(), nullable=False),
        sa.Column("user_b_id", sa.UUID(), nullable=False),
        sa.Column("state", state, server_default="none", nullable=False),
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
        sa.CheckConstraint("user_a_id < user_b_id", name=op.f("ck_collaborations_pair_is_ordered")),
        sa.ForeignKeyConstraint(
            ["user_a_id"],
            ["users.id"],
            name=op.f("fk_collaborations_user_a_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_b_id"],
            ["users.id"],
            name=op.f("fk_collaborations_user_b_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collaborations")),
        sa.UniqueConstraint("user_a_id", "user_b_id", name="uq_collaborations_pair"),
    )
    op.create_index(op.f("ix_collaborations_user_a_id"), "collaborations", ["user_a_id"])
    op.create_index(op.f("ix_collaborations_user_b_id"), "collaborations", ["user_b_id"])

    # One relationship per pair, with the strongest state its requests imply.
    op.execute(
        sa.text(
            """
            INSERT INTO collaborations (user_a_id, user_b_id, state)
            SELECT least(sender_id, recipient_id),
                   greatest(sender_id, recipient_id),
                   (CASE
                      WHEN bool_or(status = 'accepted') THEN 'active'
                      WHEN bool_or(status = 'ended')    THEN 'ended'
                      WHEN bool_or(status = 'pending')  THEN 'requested'
                      ELSE 'none'
                    END)::collaboration_state
              FROM collaboration_requests
             GROUP BY 1, 2
            """
        )
    )

    op.add_column("collaboration_requests", sa.Column("collaboration_id", sa.UUID(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE collaboration_requests cr
               SET collaboration_id = c.id
              FROM collaborations c
             WHERE c.user_a_id = least(cr.sender_id, cr.recipient_id)
               AND c.user_b_id = greatest(cr.sender_id, cr.recipient_id)
            """
        )
    )
    op.alter_column("collaboration_requests", "collaboration_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_collaboration_requests_collaboration_id_collaborations"),
        "collaboration_requests",
        "collaborations",
        ["collaboration_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_collaboration_requests_collaboration_id"),
        "collaboration_requests",
        ["collaboration_id"],
    )

    # ------------------------------------------------ conversations follow the pair
    op.add_column("conversations", sa.Column("collaboration_id", sa.UUID(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE conversations cv
               SET collaboration_id = cr.collaboration_id
              FROM collaboration_requests cr
             WHERE cr.id = cv.collaboration_request_id
            """
        )
    )

    # Merge: the oldest thread per pair keeps everything.
    op.execute(
        sa.text(
            """
            CREATE TEMP TABLE conversation_merge AS
            SELECT cv.id AS duplicate_id,
                   first_value(cv.id) OVER (
                       PARTITION BY cv.collaboration_id ORDER BY cv.created_at, cv.id
                   ) AS keeper_id
              FROM conversations cv
             WHERE cv.collaboration_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE messages m
               SET conversation_id = cm.keeper_id
              FROM conversation_merge cm
             WHERE m.conversation_id = cm.duplicate_id
               AND cm.duplicate_id <> cm.keeper_id
            """
        )
    )
    # Participants move too, and the read mark is the more cautious of the two.
    op.execute(
        sa.text(
            """
            INSERT INTO conversation_participants (conversation_id, user_id, last_read_at, muted)
            SELECT cm.keeper_id, cp.user_id, cp.last_read_at, cp.muted
              FROM conversation_participants cp
              JOIN conversation_merge cm ON cm.duplicate_id = cp.conversation_id
             WHERE cm.duplicate_id <> cm.keeper_id
            ON CONFLICT (conversation_id, user_id) DO UPDATE
               SET last_read_at = CASE
                     WHEN conversation_participants.last_read_at IS NULL
                       OR EXCLUDED.last_read_at IS NULL THEN NULL
                     ELSE least(conversation_participants.last_read_at, EXCLUDED.last_read_at)
                   END
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE conversations keeper
               SET last_message_at = sub.newest
              FROM (SELECT conversation_id, max(created_at) AS newest
                      FROM messages GROUP BY conversation_id) sub
             WHERE keeper.id = sub.conversation_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM conversations
             WHERE id IN (SELECT duplicate_id FROM conversation_merge
                           WHERE duplicate_id <> keeper_id)
            """
        )
    )
    op.execute(sa.text("DROP TABLE conversation_merge"))

    # The bare names; the metadata naming convention adds the prefixes. The old
    # foreign key and unique constraint are not dropped by name at all --
    # PostgreSQL truncated that FK's name to 63 characters, so it no longer
    # matches what generated it. Dropping the column takes both with it.
    op.drop_constraint("exactly_one_subject", "conversations", type_="check")
    op.drop_column("conversations", "collaboration_request_id")
    op.create_unique_constraint(
        "uq_conversations_collaboration", "conversations", ["collaboration_id"]
    )
    op.create_foreign_key(
        op.f("fk_conversations_collaboration_id_collaborations"),
        "conversations",
        "collaborations",
        ["collaboration_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "exactly_one_subject",
        "conversations",
        "(collaboration_id IS NULL) <> (project_id IS NULL)",
    )

    # The old index allowed one PENDING request per direction. The pair's own
    # state now decides whether a request may be made at all, so a partial
    # index per direction would only disagree with it.
    op.drop_index("uq_collaboration_requests_pending", table_name="collaboration_requests")


def downgrade() -> None:
    """Drops what was added. A merge cannot be unpicked -- see the docstring."""
    # Bare name: the metadata naming convention adds the ck_conversations_
    # prefix, so passing the full name asks for it twice.
    op.drop_constraint("exactly_one_subject", "conversations", type_="check")
    op.drop_constraint(
        op.f("fk_conversations_collaboration_id_collaborations"),
        "conversations",
        type_="foreignkey",
    )
    op.drop_constraint("uq_conversations_collaboration", "conversations", type_="unique")
    op.drop_column("conversations", "collaboration_id")
    op.add_column("conversations", sa.Column("collaboration_request_id", sa.UUID(), nullable=True))
    op.create_unique_constraint(
        "uq_conversations_collaboration", "conversations", ["collaboration_request_id"]
    )
    op.create_foreign_key(
        # Shortened deliberately: PostgreSQL truncates identifiers at 63
        # characters, and SQLAlchemy refuses to emit one that would be cut.
        "fk_conversations_collaboration_request",
        "conversations",
        "collaboration_requests",
        ["collaboration_request_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "exactly_one_subject",
        "conversations",
        "(collaboration_request_id IS NULL) <> (project_id IS NULL)",
    )
    op.drop_index(
        op.f("ix_collaboration_requests_collaboration_id"), table_name="collaboration_requests"
    )
    op.drop_constraint(
        op.f("fk_collaboration_requests_collaboration_id_collaborations"),
        "collaboration_requests",
        type_="foreignkey",
    )
    op.drop_column("collaboration_requests", "collaboration_id")
    op.drop_table("collaborations")
    sa.Enum(name="collaboration_state").drop(op.get_bind(), checkfirst=True)
    op.create_index(
        "uq_collaboration_requests_pending",
        "collaboration_requests",
        ["sender_id", "recipient_id", "project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
