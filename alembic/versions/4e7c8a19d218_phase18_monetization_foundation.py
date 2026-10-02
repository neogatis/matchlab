"""phase18 monetization foundation

Revision ID: 4e7c8a19d218
Revises: 2fb5d20a7a17
Create Date: 2026-10-02 15:27:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4e7c8a19d218"
down_revision: Union[str, Sequence[str], None] = "2fb5d20a7a17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("provider_subscription_id", sa.String(length=255), nullable=False),
        sa.Column("product_code", sa.String(length=120), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("environment", sa.String(length=24), server_default="PRODUCTION", nullable=False),
        sa.Column("auto_renew", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("provider IN ('APPLE','GOOGLE','WEB','MANUAL')", name="ck_subscriptions_provider"),
        sa.CheckConstraint("tier IN ('PREMIUM','PREMIUM_PLUS')", name="ck_subscriptions_tier"),
        sa.CheckConstraint("status IN ('ACTIVE','GRACE','BILLING_RETRY','EXPIRED','REVOKED')", name="ck_subscriptions_status"),
        sa.CheckConstraint("environment IN ('PRODUCTION','SANDBOX')", name="ck_subscriptions_environment"),
        sa.CheckConstraint(
            "current_period_start IS NULL OR current_period_end IS NULL OR current_period_start <= current_period_end",
            name="ck_subscriptions_period_order",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_subscription_id", name="uq_subscriptions_provider_external"),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"], unique=False)
    op.create_index(
        "ix_subscriptions_user_status_end",
        "subscriptions",
        ["user_id", "status", "current_period_end"],
        unique=False,
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("provider_transaction_id", sa.String(length=255), nullable=False),
        sa.Column("product_code", sa.String(length=120), nullable=False),
        sa.Column("purchase_kind", sa.String(length=24), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("environment", sa.String(length=24), server_default="PRODUCTION", nullable=False),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("provider IN ('APPLE','GOOGLE','WEB','MANUAL')", name="ck_payments_provider"),
        sa.CheckConstraint("purchase_kind IN ('SUBSCRIPTION','ONE_TIME')", name="ck_payments_kind"),
        sa.CheckConstraint("status IN ('PURCHASED','PENDING','REFUNDED','REVOKED')", name="ck_payments_status"),
        sa.CheckConstraint("environment IN ('PRODUCTION','SANDBOX')", name="ck_payments_environment"),
        sa.CheckConstraint("amount_minor IS NULL OR amount_minor >= 0", name="ck_payments_amount_nonnegative"),
        sa.CheckConstraint("currency IS NULL OR char_length(currency) = 3", name="ck_payments_currency"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_transaction_id", name="uq_payments_provider_transaction"),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"], unique=False)
    op.create_index(
        "ix_payments_user_purchased",
        "payments",
        ["user_id", "purchased_at"],
        unique=False,
    )

    op.create_table(
        "user_entitlements",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("entitlement_key", sa.String(length=80), nullable=False),
        sa.Column("scope_key", sa.String(length=160), server_default="", nullable=False),
        sa.Column("source_payment_id", sa.BigInteger(), nullable=True),
        sa.Column("source_subscription_id", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_subscription_id"], ["subscriptions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "entitlement_key", "scope_key"),
    )
    op.create_index(
        "ix_user_entitlements_active",
        "user_entitlements",
        ["user_id", "entitlement_key", "expires_at", "revoked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_entitlements_active", table_name="user_entitlements")
    op.drop_table("user_entitlements")
    op.drop_index("ix_payments_user_purchased", table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_subscriptions_user_status_end", table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_table("subscriptions")
