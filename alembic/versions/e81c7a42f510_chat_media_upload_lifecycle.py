"""chat media upload lifecycle

Revision ID: e81c7a42f510
Revises: d42f9c0a7e21
Create Date: 2026-10-07
"""

from alembic import op
import sqlalchemy as sa


revision = "e81c7a42f510"
down_revision = "d42f9c0a7e21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_media_upload_tickets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("mime", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("original_name", sa.String(length=120), server_default="", nullable=False),
        sa.Column("expected_size", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="PREPARED", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('PREPARED','CONSUMED','CANCELLED','EXPIRED')",
            name="ck_chat_media_upload_tickets_status",
        ),
        sa.CheckConstraint(
            "kind IN ('image','video','voice')",
            name="ck_chat_media_upload_tickets_kind",
        ),
        sa.CheckConstraint(
            "expected_size > 0",
            name="ck_chat_media_upload_tickets_positive_size",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(
        "ix_chat_media_upload_tickets_user_id",
        "chat_media_upload_tickets",
        ["user_id"],
    )
    op.create_index(
        "ix_chat_media_upload_tickets_conversation_id",
        "chat_media_upload_tickets",
        ["conversation_id"],
    )
    op.create_index(
        "ix_chat_media_upload_tickets_expires_at",
        "chat_media_upload_tickets",
        ["expires_at"],
    )
    op.create_index(
        "ix_chat_media_upload_tickets_status_expires",
        "chat_media_upload_tickets",
        ["status", "expires_at"],
    )
    op.create_index(
        "ix_chat_media_upload_tickets_user_conversation_status",
        "chat_media_upload_tickets",
        ["user_id", "conversation_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chat_media_upload_tickets_user_conversation_status",
        table_name="chat_media_upload_tickets",
    )
    op.drop_index(
        "ix_chat_media_upload_tickets_status_expires",
        table_name="chat_media_upload_tickets",
    )
    op.drop_index(
        "ix_chat_media_upload_tickets_expires_at",
        table_name="chat_media_upload_tickets",
    )
    op.drop_index(
        "ix_chat_media_upload_tickets_conversation_id",
        table_name="chat_media_upload_tickets",
    )
    op.drop_index(
        "ix_chat_media_upload_tickets_user_id",
        table_name="chat_media_upload_tickets",
    )
    op.drop_table("chat_media_upload_tickets")
