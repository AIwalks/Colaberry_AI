"""add_recommendations_table

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-30

Creates AI_ChatBot_Recommendations — the Recommendation Learning ledger.

One row per recommendation generated. Append-only; rows are invalidated
(is_active=False), never deleted.

Design constraints
──────────────────
- Append-only: historical recommendations are never deleted.
- recommendation_context_json is NOT NULL — a frozen snapshot of the student
  state at generation time.  Callers must supply at minimum '{}'; the column
  is intentionally strict so every recommendation is permanently auditable.
- recommendation_key is the primary learning key (granular, e.g.
  'attendance_outreach').  recommendation_type is the broad category
  (e.g. 'reach_out') retained for display only.
- No FK constraints — consistent with DeliveryLog, GovernanceReview, and
  InterventionOutcomes patterns.
- is_active server_default=1 ensures correct value on raw SQL inserts.

Indexes created
───────────────
  ix_recommendations_cbm_id              — join to TriggeredUsers
  ix_recommendations_entity_id           — student-level queries
  ix_recommendations_recommendation_key  — primary learning aggregation key
  ix_recommendations_dimension           — filter by assessment dimension
"""

from alembic import op
import sqlalchemy as sa


revision      = "0013"
down_revision = "0012"
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        "AI_ChatBot_Recommendations",

        sa.Column("id",                         sa.Integer,      primary_key=True, autoincrement=True),
        sa.Column("created_at",                 sa.DateTime,     nullable=False),
        sa.Column("updated_at",                 sa.DateTime,     nullable=False),

        # Trigger + interpretation linkage
        sa.Column("cbm_id",                     sa.Integer,      nullable=False),
        sa.Column("interpretation_id",          sa.Integer,      nullable=True),

        # Student identity
        sa.Column("entity_id",                  sa.String(100),  nullable=False),

        # Recommendation classification
        sa.Column("recommendation_type",        sa.String(50),   nullable=False),
        sa.Column("recommendation_key",         sa.String(100),  nullable=False),
        sa.Column("recommendation_text",        sa.Text,         nullable=False),

        # Context at generation time
        sa.Column("dimension",                  sa.String(50),   nullable=False),
        sa.Column("risk_level",                 sa.String(20),   nullable=False),
        sa.Column("confidence",                 sa.Float,        nullable=False),

        # Frozen student-state snapshot — NOT NULL; supply '{}' if no context available
        sa.Column("recommendation_context_json", sa.Text,        nullable=False),

        # Provenance
        sa.Column("generated_by",               sa.String(50),   nullable=False),
        sa.Column("model_name",                 sa.String(100),  nullable=True),

        # Lifecycle
        sa.Column("is_active",                  sa.Boolean,      nullable=False,
                  server_default=sa.true()),
        sa.Column("invalidated_at",             sa.DateTime,     nullable=True),
        sa.Column("invalidation_reason",        sa.Text,         nullable=True),
    )

    op.create_index(
        "ix_recommendations_cbm_id",
        "AI_ChatBot_Recommendations",
        ["cbm_id"],
    )
    op.create_index(
        "ix_recommendations_entity_id",
        "AI_ChatBot_Recommendations",
        ["entity_id"],
    )
    op.create_index(
        "ix_recommendations_recommendation_key",
        "AI_ChatBot_Recommendations",
        ["recommendation_key"],
    )
    op.create_index(
        "ix_recommendations_dimension",
        "AI_ChatBot_Recommendations",
        ["dimension"],
    )


def downgrade():
    op.drop_index("ix_recommendations_dimension",           table_name="AI_ChatBot_Recommendations")
    op.drop_index("ix_recommendations_recommendation_key",  table_name="AI_ChatBot_Recommendations")
    op.drop_index("ix_recommendations_entity_id",           table_name="AI_ChatBot_Recommendations")
    op.drop_index("ix_recommendations_cbm_id",              table_name="AI_ChatBot_Recommendations")
    op.drop_table("AI_ChatBot_Recommendations")
