"""phase11 chat message integrity

Revision ID: 6c8f1e7a4b11
Revises: 5f61abefb8d2
Create Date: 2026-10-02 13:24:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6c8f1e7a4b11"
down_revision: Union[str, Sequence[str], None] = "5f61abefb8d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("client_message_id", sa.String(length=120), nullable=True),
    )
    op.create_unique_constraint(
        "uq_messages_client_id",
        "messages",
        ["conversation_id", "sender", "client_message_id"],
    )
    op.create_check_constraint(
        "ck_messages_body_length",
        "messages",
        "char_length(btrim(body)) BETWEEN 1 AND 4000",
    )
    op.create_index(
        "ix_messages_conversation_id_id",
        "messages",
        ["conversation_id", "id"],
        unique=False,
    )
    op.create_index(
        "ix_messages_conversation_unread",
        "messages",
        ["conversation_id", "read_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_unread", table_name="messages")
    op.drop_index("ix_messages_conversation_id_id", table_name="messages")
    op.drop_constraint("ck_messages_body_length", "messages", type_="check")
    op.drop_constraint("uq_messages_client_id", "messages", type_="unique")
    op.drop_column("messages", "client_message_id")
