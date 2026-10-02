"""phase12 safety constraints

Revision ID: 9b31e9a20f12
Revises: 6c8f1e7a4b11
Create Date: 2026-10-02 13:31:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = "9b31e9a20f12"
down_revision: Union[str, Sequence[str], None] = "6c8f1e7a4b11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_users_status",
        "users",
        "status IN ('ACTIVE','SOFT_BANNED','BANNED','DELETION_REQUESTED')",
    )
    op.create_check_constraint(
        "ck_reports_status",
        "reports",
        "status IN ('OPEN','IN_REVIEW','RESOLVED','DISMISSED')",
    )
    op.create_check_constraint(
        "ck_reports_one_target",
        "reports",
        "((target_user IS NOT NULL)::int + (photo_id IS NOT NULL)::int + (message_id IS NOT NULL)::int) = 1",
    )
    op.create_index(
        "ix_reports_status_created",
        "reports",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_reports_status_created", table_name="reports")
    op.drop_constraint("ck_reports_one_target", "reports", type_="check")
    op.drop_constraint("ck_reports_status", "reports", type_="check")
    op.drop_constraint("ck_users_status", "users", type_="check")
