"""phase17 referral attribution

Revision ID: 2fb5d20a7a17
Revises: 7d61ab42e616
Create Date: 2026-10-02 15:22:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2fb5d20a7a17"
down_revision: Union[str, Sequence[str], None] = "7d61ab42e616"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "referrals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("referrer_user_id", sa.BigInteger(), nullable=True),
        sa.Column("referred_user_id", sa.BigInteger(), nullable=False),
        sa.Column("referral_code_used", sa.String(length=64), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("profile_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "referrer_user_id IS NULL OR referrer_user_id <> referred_user_id",
            name="ck_referrals_not_self",
        ),
        sa.ForeignKeyConstraint(["referrer_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["referred_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("referred_user_id"),
    )
    op.create_index(
        "ix_referrals_referrer_user_id",
        "referrals",
        ["referrer_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_referrals_referrer_registered",
        "referrals",
        ["referrer_user_id", "registered_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_referrals_referrer_registered", table_name="referrals")
    op.drop_index("ix_referrals_referrer_user_id", table_name="referrals")
    op.drop_table("referrals")
