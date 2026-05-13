"""add_student_responses_table

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-04

"""

from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "AI_ChatBot_StudentResponses",
        sa.Column("id",                  sa.Integer,     primary_key=True, autoincrement=True),
        sa.Column("cbm_id",              sa.Integer,     nullable=False),
        sa.Column("engagement_event_id", sa.Integer,     nullable=False),
        sa.Column("user_id",             sa.Integer,     nullable=False),
        sa.Column("response_channel",    sa.String(50),  nullable=False),
        sa.Column("match_method",        sa.String(30),  nullable=False),
        sa.Column("confidence",          sa.Float,       nullable=False),
        sa.Column("matched_at",          sa.DateTime,    nullable=False),
    )
    op.create_index("ix_student_responses_cbm_id",              "AI_ChatBot_StudentResponses", ["cbm_id"])
    op.create_index("ix_student_responses_engagement_event_id", "AI_ChatBot_StudentResponses", ["engagement_event_id"])
    op.create_index("ix_student_responses_user_id",             "AI_ChatBot_StudentResponses", ["user_id"])


def downgrade():
    op.drop_index("ix_student_responses_user_id",             table_name="AI_ChatBot_StudentResponses")
    op.drop_index("ix_student_responses_engagement_event_id", table_name="AI_ChatBot_StudentResponses")
    op.drop_index("ix_student_responses_cbm_id",              table_name="AI_ChatBot_StudentResponses")
    op.drop_table("AI_ChatBot_StudentResponses")
