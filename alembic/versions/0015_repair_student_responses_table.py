"""repair_student_responses_table

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-21

Repair migration — creates AI_ChatBot_StudentResponses and its three indexes
only if they are absent from the database.

Root cause
──────────
The table was first introduced in revision 0009.  On at least one database the
alembic_version row records 0014 (the current head) but the table is missing —
indicating that migration 0009 was either skipped when the version pointer was
force-advanced, or the table was dropped manually after the fact.

Because alembic_version already reads 0014, running ``alembic upgrade head``
is a no-op for Alembic.  A downgrade-then-upgrade approach would be
destructive: it would drop all Sentinel OS tables (0009 → 0014) — AI
interpretations, governance reviews, intervention outcomes, recommendations,
and candidate pools — before re-creating them.

This migration is idempotent: it inspects the live schema before touching
anything and is safe to run against databases that already have the table.

Runbook
───────
Apply this migration to the target SQL Server database:

    alembic upgrade 0015

Verify afterward:
    SELECT TOP 1 * FROM AI_ChatBot_StudentResponses;
    SELECT name FROM sys.indexes WHERE object_id = OBJECT_ID('AI_ChatBot_StudentResponses');

Downgrade removes the table only if this migration created it (idempotent
downgrade not implemented — full table drop is intentional on rollback because
this migration is the only way the table can exist when alembic_version is 0015).
"""

from alembic import op
import sqlalchemy as sa


revision      = "0015"
down_revision = "0014"
branch_labels = None
depends_on    = None


def upgrade():
    bind      = op.get_bind()
    inspector = sa.inspect(bind)

    existing_tables  = set(inspector.get_table_names())
    table_missing    = "AI_ChatBot_StudentResponses" not in existing_tables

    if table_missing:
        op.create_table(
            "AI_ChatBot_StudentResponses",
            sa.Column("id",                  sa.Integer,     primary_key=True, autoincrement=True),
            sa.Column("cbm_id",              sa.Integer,     nullable=False),
            sa.Column("engagement_event_id", sa.Integer,     nullable=False),
            sa.Column("user_id",             sa.Integer,     nullable=False),
            sa.Column("response_channel",    sa.String(50),  nullable=False),
            sa.Column("match_method",        sa.String(30),  nullable=False),
            sa.Column("confidence",          sa.Float,       nullable=False),
            sa.Column("matched_at",          sa.DateTime,    nullable=True),
        )
        # Create all three indexes — they can only exist if the table was just
        # created, so no need to check index existence separately.
        op.create_index(
            "ix_student_responses_cbm_id",
            "AI_ChatBot_StudentResponses",
            ["cbm_id"],
        )
        op.create_index(
            "ix_student_responses_engagement_event_id",
            "AI_ChatBot_StudentResponses",
            ["engagement_event_id"],
        )
        op.create_index(
            "ix_student_responses_user_id",
            "AI_ChatBot_StudentResponses",
            ["user_id"],
        )
    else:
        # Table exists — ensure all three indexes are present.
        # This handles the edge case where the table was partially repaired.
        existing_indexes = {
            idx["name"]
            for idx in inspector.get_indexes("AI_ChatBot_StudentResponses")
        }
        index_map = {
            "ix_student_responses_cbm_id":              ["cbm_id"],
            "ix_student_responses_engagement_event_id": ["engagement_event_id"],
            "ix_student_responses_user_id":             ["user_id"],
        }
        for index_name, columns in index_map.items():
            if index_name not in existing_indexes:
                op.create_index(
                    index_name,
                    "AI_ChatBot_StudentResponses",
                    columns,
                )


def downgrade():
    op.drop_index("ix_student_responses_user_id",             table_name="AI_ChatBot_StudentResponses")
    op.drop_index("ix_student_responses_engagement_event_id", table_name="AI_ChatBot_StudentResponses")
    op.drop_index("ix_student_responses_cbm_id",              table_name="AI_ChatBot_StudentResponses")
    op.drop_table("AI_ChatBot_StudentResponses")
