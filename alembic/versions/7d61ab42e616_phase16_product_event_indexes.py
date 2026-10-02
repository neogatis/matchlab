"""phase16 product event indexes

Revision ID: 7d61ab42e616
Revises: 1a7d3f48ce13
"""
from typing import Sequence, Union

from alembic import op


revision: str = "7d61ab42e616"
down_revision: Union[str, Sequence[str], None] = "1a7d3f48ce13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_product_events_user_created",
        "product_events",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_product_events_type_created",
        "product_events",
        ["event_type", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_product_events_type_created", table_name="product_events")
    op.drop_index("ix_product_events_user_created", table_name="product_events")
