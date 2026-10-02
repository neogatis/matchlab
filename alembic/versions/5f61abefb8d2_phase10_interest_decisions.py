"""phase10 interest decisions

Revision ID: 5f61abefb8d2
Revises: 366eef283443
Create Date: 2026-10-02 12:57:52
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5f61abefb8d2"
down_revision: Union[str, Sequence[str], None] = "366eef283443"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interests",
        sa.Column("source_algorithm_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "interests",
        sa.Column("snooze_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "interests",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        """
        UPDATE interests
        SET updated_at = created_at,
            source_algorithm_version = COALESCE(source_algorithm_version, 'legacy-v7')
        """
    )
    op.alter_column(
        "interests",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    op.create_check_constraint(
        "ck_interests_not_self",
        "interests",
        "from_user <> to_user",
    )
    op.create_check_constraint(
        "ck_interests_state",
        "interests",
        "state IN ('INTERESTED','SKIPPED')",
    )
    op.create_index(
        "ix_interests_from_state_snooze",
        "interests",
        ["from_user", "state", "snooze_until"],
        unique=False,
    )
    op.create_index(
        "ix_interests_to_state",
        "interests",
        ["to_user", "state"],
        unique=False,
    )

    op.execute(
        """
        UPDATE matches
        SET user1 = LEAST(user1, user2),
            user2 = GREATEST(user1, user2)
        WHERE user1 > user2
        """
    )
    op.create_check_constraint(
        "ck_matches_canonical_pair",
        "matches",
        "user1 < user2",
    )


def downgrade() -> None:
    op.drop_constraint("ck_matches_canonical_pair", "matches", type_="check")
    op.drop_index("ix_interests_to_state", table_name="interests")
    op.drop_index("ix_interests_from_state_snooze", table_name="interests")
    op.drop_constraint("ck_interests_state", "interests", type_="check")
    op.drop_constraint("ck_interests_not_self", "interests", type_="check")
    op.drop_column("interests", "updated_at")
    op.drop_column("interests", "snooze_until")
    op.drop_column("interests", "source_algorithm_version")
