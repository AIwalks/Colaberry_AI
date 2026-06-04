"""add_intervention_outcomes_table

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-28

Creates AI_ChatBot_InterventionOutcomes — the Outcome Learning ledger.

One row per fired trigger. Records the before-state at enrollment time,
the after-state when the evaluation window closes, and the computed
outcome label ('improved', 'not_improved', or 'inconclusive').

Design constraints
──────────────────
- One row per trigger: cbm_id UNIQUE.
- Records transition from 'pending' → final outcome; never deleted.
- before_snapshot_source documents where the before-state was read from.
- No FK constraints — consistent with DeliveryLog and GovernanceReview patterns.
- delivery_gate_passed must be True for any non-inconclusive outcome.

Defaults applied via server_default
─────────────────────────────────────
  evaluation_window_days   14
  delivery_gate_passed     FALSE
  before_snapshot_source   'unavailable'
  outcome                  'pending'

Indexes created
───────────────
  uq_intervention_outcomes_cbm_id              — UNIQUE; dedup gate (one row per trigger)
  ix_intervention_outcomes_user_id             — student-level queries
  ix_intervention_outcomes_interpretation_id   — join to AIInterpretations
  ix_intervention_outcomes_eligible_for_learning — learning filter
  ix_intervention_outcomes_outcome_window_end  — COMPOSITE; scheduler query:
                                                  WHERE outcome = 'pending'
                                                  AND window_end <= NOW()
"""

from alembic import op
import sqlalchemy as sa


revision     = "0012"
down_revision = "0011"
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        "AI_ChatBot_InterventionOutcomes",

        sa.Column("id",                         sa.Integer,     primary_key=True, autoincrement=True),
        sa.Column("created_at",                 sa.DateTime,    nullable=False),
        sa.Column("updated_at",                 sa.DateTime,    nullable=False),

        # Intervention identity
        sa.Column("cbm_id",                     sa.Integer,     nullable=False),
        sa.Column("user_id",                    sa.Integer,     nullable=True),
        sa.Column("interpretation_id",          sa.Integer,     nullable=True),

        # Evaluation window
        sa.Column("window_start",               sa.DateTime,    nullable=False),
        sa.Column("window_end",                 sa.DateTime,    nullable=False),
        sa.Column("evaluation_window_days",     sa.Integer,     nullable=False,
                  server_default="14"),

        # Delivery gate
        sa.Column("delivery_gate_passed",       sa.Boolean,     nullable=False,
                  server_default=sa.false()),

        # Before-state (captured at enrollment)
        sa.Column("before_last_activity_days",  sa.Integer,     nullable=True),
        sa.Column("before_risk_level",          sa.String(20),  nullable=True),
        sa.Column("before_snapshot_source",     sa.String(30),  nullable=False,
                  server_default="unavailable"),

        # After-state (populated by evaluation job)
        sa.Column("after_last_activity_days",   sa.Integer,     nullable=True),
        sa.Column("after_risk_level",           sa.String(20),  nullable=True),
        sa.Column("after_captured_at",          sa.DateTime,    nullable=True),

        # Outcome
        sa.Column("outcome",                    sa.String(20),  nullable=False,
                  server_default="pending"),
        sa.Column("outcome_reason",             sa.String(300), nullable=True),
        sa.Column("eligible_for_learning",      sa.Boolean,     nullable=True),
        sa.Column("evaluated_at",               sa.DateTime,    nullable=True),
    )

    # UNIQUE — one evaluation per trigger; also serves as a fast lookup index
    op.create_index(
        "uq_intervention_outcomes_cbm_id",
        "AI_ChatBot_InterventionOutcomes",
        ["cbm_id"],
        unique=True,
    )
    op.create_index(
        "ix_intervention_outcomes_user_id",
        "AI_ChatBot_InterventionOutcomes",
        ["user_id"],
    )
    op.create_index(
        "ix_intervention_outcomes_interpretation_id",
        "AI_ChatBot_InterventionOutcomes",
        ["interpretation_id"],
    )
    op.create_index(
        "ix_intervention_outcomes_eligible_for_learning",
        "AI_ChatBot_InterventionOutcomes",
        ["eligible_for_learning"],
    )
    # Composite — the scheduler query: WHERE outcome = 'pending' AND window_end <= NOW()
    op.create_index(
        "ix_intervention_outcomes_outcome_window_end",
        "AI_ChatBot_InterventionOutcomes",
        ["outcome", "window_end"],
    )


def downgrade():
    op.drop_index(
        "ix_intervention_outcomes_outcome_window_end",
        table_name="AI_ChatBot_InterventionOutcomes",
    )
    op.drop_index(
        "ix_intervention_outcomes_eligible_for_learning",
        table_name="AI_ChatBot_InterventionOutcomes",
    )
    op.drop_index(
        "ix_intervention_outcomes_interpretation_id",
        table_name="AI_ChatBot_InterventionOutcomes",
    )
    op.drop_index(
        "ix_intervention_outcomes_user_id",
        table_name="AI_ChatBot_InterventionOutcomes",
    )
    op.drop_index(
        "uq_intervention_outcomes_cbm_id",
        table_name="AI_ChatBot_InterventionOutcomes",
    )
    op.drop_table("AI_ChatBot_InterventionOutcomes")
