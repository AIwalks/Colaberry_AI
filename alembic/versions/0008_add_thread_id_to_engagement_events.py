"""add_thread_id_to_engagement_events

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-04

"""

from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "AI_ChatBot_EngagementEvents",
        sa.Column("thread_id", sa.String(255), nullable=True),
    )


def downgrade():
    op.drop_column("AI_ChatBot_EngagementEvents", "thread_id")
