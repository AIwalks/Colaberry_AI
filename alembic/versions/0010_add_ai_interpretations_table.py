"""add_ai_interpretations_table

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-12

Creates AI_ChatBot_AIInterpretations — the Interpretation Persistence Layer.

Design constraints
──────────────────
- Append-only: rows are invalidated (is_active=False), never deleted.
- explainability_json and source_snapshot_json stored as Text (JSON strings);
  callers serialize/deserialize with json.dumps/json.loads.
- source_metrics_hash (SHA-256 hex, 64 chars) indexed for reuse detection.
- stale_after defaults to INSERT time + 14 days; set by the ORM default function,
  not by a server_default, because the value is computed in Python.
- is_active server_default=true ensures correct value even on raw SQL inserts.

Indexes created
───────────────
  ix_ai_interpretations_entity_id          — primary lookup by student
  ix_ai_interpretations_entity_type        — filter by entity class
  ix_ai_interpretations_source_metrics_hash — reuse detection query
  ix_ai_interpretations_is_active          — filter active-only
  ix_ai_interpretations_dimension          — filter by assessment dimension
"""

from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "AI_ChatBot_AIInterpretations",
        sa.Column("id",                     sa.Integer,     primary_key=True, autoincrement=True),
        sa.Column("created_at",             sa.DateTime,    nullable=False),
        sa.Column("updated_at",             sa.DateTime,    nullable=False),
        sa.Column("invalidated_at",         sa.DateTime,    nullable=True),

        sa.Column("entity_id",              sa.String(100), nullable=False),
        sa.Column("entity_type",            sa.String(50),  nullable=False),

        sa.Column("dimension",              sa.String(50),  nullable=False),
        sa.Column("interpretation_version", sa.Integer,     nullable=False, server_default="1"),

        sa.Column("confidence",             sa.Float,       nullable=False),
        sa.Column("risk_level",             sa.String(20),  nullable=False),

        sa.Column("summary",                sa.Text,        nullable=False),
        sa.Column("recommended_action",     sa.Text,        nullable=True),

        sa.Column("explainability_json",    sa.Text,        nullable=True),
        sa.Column("source_metrics_hash",    sa.String(64),  nullable=True),
        sa.Column("source_snapshot_json",   sa.Text,        nullable=True),

        sa.Column("generated_by",           sa.String(30),  nullable=False),
        sa.Column("model_name",             sa.String(100), nullable=True),

        sa.Column("stale_after",            sa.DateTime,    nullable=True),
        sa.Column("is_active",              sa.Boolean,     nullable=False, server_default=sa.true()),
        sa.Column("invalidation_reason",    sa.Text,        nullable=True),
    )

    op.create_index(
        "ix_ai_interpretations_entity_id",
        "AI_ChatBot_AIInterpretations",
        ["entity_id"],
    )
    op.create_index(
        "ix_ai_interpretations_entity_type",
        "AI_ChatBot_AIInterpretations",
        ["entity_type"],
    )
    op.create_index(
        "ix_ai_interpretations_source_metrics_hash",
        "AI_ChatBot_AIInterpretations",
        ["source_metrics_hash"],
    )
    op.create_index(
        "ix_ai_interpretations_is_active",
        "AI_ChatBot_AIInterpretations",
        ["is_active"],
    )
    op.create_index(
        "ix_ai_interpretations_dimension",
        "AI_ChatBot_AIInterpretations",
        ["dimension"],
    )


def downgrade():
    op.drop_index("ix_ai_interpretations_dimension",           table_name="AI_ChatBot_AIInterpretations")
    op.drop_index("ix_ai_interpretations_is_active",           table_name="AI_ChatBot_AIInterpretations")
    op.drop_index("ix_ai_interpretations_source_metrics_hash", table_name="AI_ChatBot_AIInterpretations")
    op.drop_index("ix_ai_interpretations_entity_type",         table_name="AI_ChatBot_AIInterpretations")
    op.drop_index("ix_ai_interpretations_entity_id",           table_name="AI_ChatBot_AIInterpretations")
    op.drop_table("AI_ChatBot_AIInterpretations")
