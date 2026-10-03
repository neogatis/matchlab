from __future__ import annotations

import os
import subprocess
import sys

from app.db.models import Setting
from app.db.session import make_engine
from app.profile.service import ensure_market
from app.questionnaire.service import seed_v7_questionnaire
from sqlalchemy.orm import sessionmaker


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def migrate() -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
    )


def seed_runtime() -> None:
    engine = make_engine()
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session.begin() as db:
        seed_v7_questionnaire(db, activate=True)

        setting = db.get(Setting, "PRE_LAUNCH_MODE")
        value = "true" if _bool_env("PRE_LAUNCH_MODE", True) else "false"
        if setting is None:
            db.add(Setting(key="PRE_LAUNCH_MODE", value=value))
        else:
            setting.value = value

        market_code = os.environ.get("BOOTSTRAP_MARKET_CODE", "").strip()
        if market_code:
            required = {
                "BOOTSTRAP_MARKET_COUNTRY": os.environ.get("BOOTSTRAP_MARKET_COUNTRY", "").strip(),
                "BOOTSTRAP_MARKET_CITY": os.environ.get("BOOTSTRAP_MARKET_CITY", "").strip(),
                "BOOTSTRAP_MARKET_NAME": os.environ.get("BOOTSTRAP_MARKET_NAME", "").strip(),
            }
            missing = [key for key, value in required.items() if not value]
            if missing:
                raise RuntimeError(
                    "Market bootstrap is incomplete: " + ", ".join(missing)
                )
            ensure_market(
                db,
                code=market_code,
                country_code=required["BOOTSTRAP_MARKET_COUNTRY"],
                city_code=required["BOOTSTRAP_MARKET_CITY"],
                display_name=required["BOOTSTRAP_MARKET_NAME"],
                timezone_name=os.environ.get("BOOTSTRAP_MARKET_TIMEZONE", "Asia/Almaty"),
                currency_code=os.environ.get("BOOTSTRAP_MARKET_CURRENCY", "KZT"),
                default_language=os.environ.get("BOOTSTRAP_MARKET_LANGUAGE", "ru-KZ"),
                supported_languages=[
                    item.strip()
                    for item in os.environ.get(
                        "BOOTSTRAP_MARKET_LANGUAGES", "ru-KZ,kk-KZ"
                    ).split(",")
                    if item.strip()
                ],
                registration_open=_bool_env("BOOTSTRAP_MARKET_REGISTRATION_OPEN", True),
                matching_open=_bool_env("BOOTSTRAP_MARKET_MATCHING_OPEN", False),
            )


def main() -> None:
    if not os.environ.get("DATABASE_URL", "").strip():
        raise RuntimeError("DATABASE_URL is required")
    migrate()
    seed_runtime()

    from app.http.server import main as serve

    serve()


if __name__ == "__main__":
    main()
