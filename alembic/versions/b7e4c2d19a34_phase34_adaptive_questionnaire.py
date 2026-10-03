"""phase34 adaptive questionnaire

Revision ID: b7e4c2d19a34
Revises: 8a31df90c219
Create Date: 2026-10-03 16:20:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b7e4c2d19a34"
down_revision: Union[str, Sequence[str], None] = "8a31df90c219"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "adaptive_questionnaire_questions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("axis_key", sa.String(length=64), nullable=False),
        sa.Column("category_key", sa.String(length=64), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), server_default="BANK", nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "generator_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('BANK','OPENAI')",
            name="ck_adaptive_questions_source",
        ),
        sa.CheckConstraint(
            "position > 0",
            name="ck_adaptive_questions_position_positive",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "position",
            name="uq_adaptive_questions_user_position",
        ),
    )
    op.create_index(
        "ix_adaptive_questionnaire_questions_user_id",
        "adaptive_questionnaire_questions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_adaptive_questions_user_axis",
        "adaptive_questionnaire_questions",
        ["user_id", "axis_key"],
        unique=False,
    )

    op.create_table(
        "adaptive_questionnaire_answers",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("adaptive_question_id", sa.BigInteger(), nullable=False),
        sa.Column("value_int", sa.Integer(), nullable=False),
        sa.Column(
            "answered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "value_int BETWEEN 1 AND 5",
            name="ck_adaptive_answers_scale",
        ),
        sa.ForeignKeyConstraint(
            ["adaptive_question_id"],
            ["adaptive_questionnaire_questions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "adaptive_question_id"),
    )
    op.create_index(
        "ix_adaptive_answers_user_answered",
        "adaptive_questionnaire_answers",
        ["user_id", "answered_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_adaptive_answers_user_answered",
        table_name="adaptive_questionnaire_answers",
    )
    op.drop_table("adaptive_questionnaire_answers")
    op.drop_index(
        "ix_adaptive_questions_user_axis",
        table_name="adaptive_questionnaire_questions",
    )
    op.drop_index(
        "ix_adaptive_questionnaire_questions_user_id",
        table_name="adaptive_questionnaire_questions",
    )
    op.drop_table("adaptive_questionnaire_questions")
