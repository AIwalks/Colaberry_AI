"""add_generated_insights_table

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-25

"""

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "AI_ChatBot_GeneratedInsights",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("insight_type", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column("source_kpis_json", sa.Text, nullable=True),
        sa.Column("source_patterns_json", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.func.now(),
        ),
    )


def downgrade():
    op.drop_table("AI_ChatBot_GeneratedInsights")
