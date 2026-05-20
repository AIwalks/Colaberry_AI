"""add_governance_reviews_table

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-18

Creates AI_ChatBot_GovernanceReviews — the human-governed review queue for
AI-generated interpretations.

Design constraints
──────────────────
- Append-only: rows are never deleted; is_active=False reserved for supersession.
- audit_snapshot_json stored as Text (JSON string); immutable after creation.
- interpretation_id references AI_ChatBot_AIInterpretations.id (no FK constraint
  to avoid cross-table dependency on SQL Server with schema isolation).
- status server_default="pending" ensures correct value on raw SQL inserts.
- reviewed_by, reviewed_at, review_notes are nullable — set only on decision.

Indexes created
───────────────
  ix_governance_reviews_entity_id         — primary lookup by student
  ix_governance_reviews_interpretation_id — join to AIInterpretation
  ix_governance_reviews_status            — filter queue by status
  ix_governance_reviews_is_active         — filter active reviews
"""

from alembic import op
import sqlalchemy as sa


revision     = "0011"
down_revision = "0010"
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        "AI_ChatBot_GovernanceReviews",
        sa.Column("id",                  sa.Integer,     primary_key=True, autoincrement=True),
        sa.Column("created_at",          sa.DateTime,    nullable=False),
        sa.Column("updated_at",          sa.DateTime,    nullable=False),

        sa.Column("interpretation_id",   sa.Integer,     nullable=False),
        sa.Column("entity_id",           sa.String(100), nullable=False),
        sa.Column("entity_type",         sa.String(50),  nullable=False),

        sa.Column("status",              sa.String(20),  nullable=False,
                  server_default="pending"),

        sa.Column("reviewed_by",         sa.String(200), nullable=True),
        sa.Column("reviewed_at",         sa.DateTime,    nullable=True),
        sa.Column("review_notes",        sa.Text,        nullable=True),

        sa.Column("governance_reason",   sa.Text,        nullable=False),
        sa.Column("risk_level",          sa.String(20),  nullable=False),
        sa.Column("confidence",          sa.Float,       nullable=False),

        sa.Column("audit_snapshot_json", sa.Text,        nullable=True),
        sa.Column("is_active",           sa.Boolean,     nullable=False,
                  server_default=sa.true()),
    )

    op.create_index(
        "ix_governance_reviews_entity_id",
        "AI_ChatBot_GovernanceReviews",
        ["entity_id"],
    )
    op.create_index(
        "ix_governance_reviews_interpretation_id",
        "AI_ChatBot_GovernanceReviews",
        ["interpretation_id"],
    )
    op.create_index(
        "ix_governance_reviews_status",
        "AI_ChatBot_GovernanceReviews",
        ["status"],
    )
    op.create_index(
        "ix_governance_reviews_is_active",
        "AI_ChatBot_GovernanceReviews",
        ["is_active"],
    )


def downgrade():
    op.drop_index("ix_governance_reviews_is_active",         table_name="AI_ChatBot_GovernanceReviews")
    op.drop_index("ix_governance_reviews_status",            table_name="AI_ChatBot_GovernanceReviews")
    op.drop_index("ix_governance_reviews_interpretation_id", table_name="AI_ChatBot_GovernanceReviews")
    op.drop_index("ix_governance_reviews_entity_id",         table_name="AI_ChatBot_GovernanceReviews")
    op.drop_table("AI_ChatBot_GovernanceReviews")
