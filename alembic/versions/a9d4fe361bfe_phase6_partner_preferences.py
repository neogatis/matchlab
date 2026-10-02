"""phase6 partner preferences

Revision ID: a9d4fe361bfe
Revises: 0e20b2694ed6
Create Date: 2026-10-02 12:06:03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a9d4fe361bfe"
down_revision: Union[str, Sequence[str], None] = "0e20b2694ed6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column(
            "partner_preferences_completed",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_partner_preferences_range_order",
        "partner_preferences",
        "min_value IS NULL OR max_value IS NULL OR min_value <= max_value",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_partner_preferences_range_order",
        "partner_preferences",
        type_="check",
    )
    op.drop_column("profiles", "partner_preferences_completed")
