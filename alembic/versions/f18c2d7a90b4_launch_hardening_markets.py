"""launch hardening: Kazakhstan registration markets

Revision ID: f18c2d7a90b4
Revises: b7e4c2d19a34
Create Date: 2026-10-04
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f18c2d7a90b4"
down_revision: Union[str, Sequence[str], None] = "b7e4c2d19a34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO markets (
            code, country_code, city_code, display_name, timezone,
            currency_code, default_language, latitude, longitude,
            supported_languages, registration_open, matching_open
        )
        VALUES
            ('KZ-AST','KZ','AST','Астана','Asia/Almaty','KZT','ru-KZ',
             51.169392,71.449074,'["ru-KZ","kk-KZ"]'::jsonb,true,false),
            ('KZ-CIT','KZ','CIT','Шымкент','Asia/Almaty','KZT','ru-KZ',
             42.341700,69.590100,'["ru-KZ","kk-KZ"]'::jsonb,true,false),
            ('KZ-KGF','KZ','KGF','Караганда','Asia/Almaty','KZT','ru-KZ',
             49.806406,73.085485,'["ru-KZ","kk-KZ"]'::jsonb,true,false),
            ('KZ-OTHER','KZ','OTHER','Другой город','Asia/Almaty','KZT','ru-KZ',
             NULL,NULL,'["ru-KZ","kk-KZ"]'::jsonb,true,false)
        ON CONFLICT (code) DO UPDATE SET
            country_code = EXCLUDED.country_code,
            city_code = EXCLUDED.city_code,
            display_name = EXCLUDED.display_name,
            timezone = EXCLUDED.timezone,
            currency_code = EXCLUDED.currency_code,
            default_language = EXCLUDED.default_language,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            supported_languages = EXCLUDED.supported_languages,
            registration_open = EXCLUDED.registration_open,
            matching_open = EXCLUDED.matching_open,
            updated_at = now()
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM markets WHERE code IN ('KZ-AST','KZ-CIT','KZ-KGF','KZ-OTHER')"
    )
