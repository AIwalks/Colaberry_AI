"""add_engagement_events_table

Revision ID: 0001
Revises: 
Create Date: 2026-03-12 09:08:17.048436

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "AI_ChatBot_EngagementEvents",
        sa.Column("id",         sa.Integer,     primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id",    sa.Integer,     nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("channel",    sa.String(50),  nullable=True),
        sa.Column("message",    sa.Text,        nullable=True),
        sa.Column("agent_name", sa.String(100), nullable=True),
        sa.Column("trigger_id", sa.Integer,     nullable=True),
        sa.Column("created_at", sa.DateTime,    nullable=True),
    )


def downgrade() -> None:
    op.drop_table("AI_ChatBot_EngagementEvents")
