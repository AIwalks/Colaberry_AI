"""add_recommendation_candidate_pools

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-30

Creates AI_ChatBot_RecommendationCandidatePools — governance-controlled pool
definitions that map a trigger context (trigger_type + dimension) to an ordered
set of candidate recommendation keys.

Design constraints
──────────────────
- One pool per (trigger_type, dimension) pair — enforced by a composite unique
  index.  To update a pool, UPDATE the existing row; do not insert a duplicate.
- candidate_keys_json is NOT NULL — must contain at minimum a valid JSON array
  ('[]').  The service layer serializes / deserializes; never store raw text.
- Soft-disable via is_active=False; rows are never deleted so the pool
  definition history is preserved.
- min_sample_override and epsilon_override are nullable.  NULL means: use the
  system-wide default (min_sample=10, epsilon=0.05) defined in
  AdaptiveRecommendationService.
- No FK constraints — consistent with the FK-style reference pattern used by
  all other Sentinel tables.

Indexes created
───────────────
  uq_candidate_pools_trigger_dimension — composite unique (trigger_type, dimension);
                                          the primary lookup key for every pool read
  ix_candidate_pools_is_active         — fast filter for active pools
"""

from alembic import op
import sqlalchemy as sa


revision      = "0014"
down_revision = "0013"
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        "AI_ChatBot_RecommendationCandidatePools",

        sa.Column("id",                   sa.Integer,     primary_key=True, autoincrement=True),
        sa.Column("created_at",           sa.DateTime,    nullable=False),
        sa.Column("updated_at",           sa.DateTime,    nullable=False),

        # Trigger context — composite unique enforced by index below
        sa.Column("trigger_type",         sa.String(50),  nullable=False),
        sa.Column("dimension",            sa.String(50),  nullable=False),

        # Ordered JSON array of recommendation_key strings
        # e.g. '["attendance_personal_outreach", "attendance_deadline_reminder"]'
        sa.Column("candidate_keys_json",  sa.Text,        nullable=False),

        # Per-pool overrides — NULL falls back to system defaults
        sa.Column("min_sample_override",  sa.Integer,     nullable=True),
        sa.Column("epsilon_override",     sa.Float,       nullable=True),

        # Lifecycle
        sa.Column("is_active",            sa.Boolean,     nullable=False,
                  server_default=sa.true()),
    )

    # Composite unique — one pool definition per trigger context.
    # Named consistently with the uq_ prefix used by InterventionOutcomes.
    op.create_index(
        "uq_candidate_pools_trigger_dimension",
        "AI_ChatBot_RecommendationCandidatePools",
        ["trigger_type", "dimension"],
        unique=True,
    )

    op.create_index(
        "ix_candidate_pools_is_active",
        "AI_ChatBot_RecommendationCandidatePools",
        ["is_active"],
    )


def downgrade():
    op.drop_index("ix_candidate_pools_is_active",         table_name="AI_ChatBot_RecommendationCandidatePools")
    op.drop_index("uq_candidate_pools_trigger_dimension",  table_name="AI_ChatBot_RecommendationCandidatePools")
    op.drop_table("AI_ChatBot_RecommendationCandidatePools")
