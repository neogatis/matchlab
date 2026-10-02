"""phase13 console rbac

Revision ID: 1a7d3f48ce13
Revises: 9b31e9a20f12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1a7d3f48ce13"
down_revision: Union[str, Sequence[str], None] = "9b31e9a20f12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_accounts",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=24), server_default="VIEWER", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "role IN ('VIEWER','MODERATOR','ADMIN','SUPERADMIN')",
            name="ck_admin_accounts_role",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        "ix_admin_accounts_active_role",
        "admin_accounts",
        ["is_active", "role"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_admin_accounts_active_role", table_name="admin_accounts")
    op.drop_table("admin_accounts")
