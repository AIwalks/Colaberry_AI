"""add_directives_table

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "AI_ChatBot_Directives",
        sa.Column("id",         sa.Integer,      primary_key=True, autoincrement=True, nullable=False),
        sa.Column("name",       sa.String(100),  nullable=False,   unique=True),
        sa.Column("content",    sa.Text,         nullable=True),
        sa.Column("version",    sa.Integer,      nullable=True),
        sa.Column("created_at", sa.DateTime,     nullable=True),
        sa.Column("updated_at", sa.DateTime,     nullable=True),
    )
    op.create_index("ix_directives_name", "AI_ChatBot_Directives", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_directives_name", table_name="AI_ChatBot_Directives")
    op.drop_table("AI_ChatBot_Directives")
