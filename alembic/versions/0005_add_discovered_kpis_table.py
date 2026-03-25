"""add_discovered_kpis_table

Revision ID: 0005
Revises: 0004
Create Date: 2025-01-01

"""

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "AI_ChatBot_DiscoveredKPIs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kpi_name", sa.String(100)),
        sa.Column("source_pattern", sa.String(100)),
        sa.Column("entity_type", sa.String(50)),
        sa.Column("formula", sa.Text),
        sa.Column("confidence", sa.Float),
        sa.Column("sample_size", sa.Integer),
        sa.Column(
            "discovered_at",
            sa.DateTime,
            server_default=sa.func.now(),
        ),
    )


def downgrade():
    op.drop_table("AI_ChatBot_DiscoveredKPIs")
