"""identity verification selfie and one-photo minimum

Revision ID: d42f9c0a7e21
Revises: b7e4c2d19a34
Create Date: 2026-10-07 16:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d42f9c0a7e21"
down_revision: Union[str, Sequence[str], None] = "b7e4c2d19a34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column(
            "identity_verification_status",
            sa.String(length=24),
            server_default="NOT_STARTED",
            nullable=False,
        ),
    )
    op.add_column(
        "profiles",
        sa.Column("identity_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_profiles_identity_verification_status",
        "profiles",
        "identity_verification_status IN ('NOT_STARTED','PENDING','VERIFIED','REJECTED')",
    )

    op.add_column(
        "photo_upload_tickets",
        sa.Column(
            "purpose",
            sa.String(length=24),
            server_default="PROFILE",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_photo_upload_tickets_purpose",
        "photo_upload_tickets",
        "purpose IN ('PROFILE','IDENTITY')",
    )

    op.add_column(
        "photos",
        sa.Column(
            "purpose",
            sa.String(length=24),
            server_default="PROFILE",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_photos_purpose",
        "photos",
        "purpose IN ('PROFILE','IDENTITY')",
    )
    op.create_index(
        "ix_photos_user_purpose_status",
        "photos",
        ["user_id", "purpose", "moderation_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_photos_user_purpose_status", table_name="photos")
    op.drop_constraint("ck_photos_purpose", "photos", type_="check")
    op.drop_column("photos", "purpose")

    op.drop_constraint(
        "ck_photo_upload_tickets_purpose",
        "photo_upload_tickets",
        type_="check",
    )
    op.drop_column("photo_upload_tickets", "purpose")

    op.drop_constraint(
        "ck_profiles_identity_verification_status",
        "profiles",
        type_="check",
    )
    op.drop_column("profiles", "identity_verified_at")
    op.drop_column("profiles", "identity_verification_status")
