"""add_delivery_log_table

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "AI_ChatBot_DeliveryLog",
        sa.Column("id",            sa.Integer,     primary_key=True, autoincrement=True, nullable=False),
        sa.Column("cbm_id",        sa.Integer,     nullable=True),
        sa.Column("user_id",       sa.Integer,     nullable=True),
        sa.Column("channel",       sa.String(50),  nullable=True),
        sa.Column("success",       sa.Boolean,     nullable=True),
        sa.Column("error_message", sa.Text,        nullable=True),
        sa.Column("created_on",    sa.DateTime,    nullable=True),
    )
    op.create_index("ix_delivery_log_cbm_id", "AI_ChatBot_DeliveryLog", ["cbm_id"])


def downgrade() -> None:
    op.drop_index("ix_delivery_log_cbm_id", table_name="AI_ChatBot_DeliveryLog")
    op.drop_table("AI_ChatBot_DeliveryLog")
