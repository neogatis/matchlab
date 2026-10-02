"""phase19 push notifications

Revision ID: 8a31df90c219
Revises: 4e7c8a19d218
Create Date: 2026-10-02 15:41:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8a31df90c219"
down_revision: Union[str, Sequence[str], None] = "4e7c8a19d218"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_devices",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_ref", sa.String(length=255), nullable=False),
        sa.Column("locale", sa.String(length=16), server_default="ru-KZ", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("provider IN ('APNS','FCM')", name="ck_push_devices_provider"),
        sa.CheckConstraint("platform IN ('IOS','ANDROID')", name="ck_push_devices_platform"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "token_hash", name="uq_push_devices_provider_token"),
    )
    op.create_index("ix_push_devices_user_id", "push_devices", ["user_id"], unique=False)
    op.create_index("ix_push_devices_user_enabled", "push_devices", ["user_id", "enabled"], unique=False)

    op.create_table(
        "push_deliveries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("notification_id", sa.BigInteger(), nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="PENDING", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('PENDING','SENDING','SENT','FAILED','DISABLED')", name="ck_push_deliveries_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_push_deliveries_attempts_nonnegative"),
        sa.ForeignKeyConstraint(["device_id"], ["push_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notification_id", "device_id", name="uq_push_delivery_notification_device"),
    )
    op.create_index(
        "ix_push_deliveries_dispatch",
        "push_deliveries",
        ["status", "next_attempt_at", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_push_deliveries_dispatch", table_name="push_deliveries")
    op.drop_table("push_deliveries")
    op.drop_index("ix_push_devices_user_enabled", table_name="push_devices")
    op.drop_index("ix_push_devices_user_id", table_name="push_devices")
    op.drop_table("push_devices")
