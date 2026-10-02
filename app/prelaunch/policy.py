from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Setting


DEFAULT_PRE_LAUNCH_MODE = True
DEFAULT_PRELAUNCH_MATCHING_ENABLED = False


def _setting_bool(db: Session, key: str, default: bool) -> bool:
    row = db.get(Setting, key)
    if row is None:
        return default
    value = (row.value or "").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def prelaunch_mode(db: Session) -> bool:
    return _setting_bool(db, "PRE_LAUNCH_MODE", DEFAULT_PRE_LAUNCH_MODE)


def controlled_matching_enabled(db: Session) -> bool:
    return _setting_bool(
        db,
        "PRELAUNCH_MATCHING_ENABLED",
        DEFAULT_PRELAUNCH_MATCHING_ENABLED,
    )


def candidate_output_enabled(db: Session) -> bool:
    if not prelaunch_mode(db):
        return True
    return controlled_matching_enabled(db)


def feature_flags(db: Session) -> dict[str, bool]:
    prelaunch = prelaunch_mode(db)
    matching = candidate_output_enabled(db)
    return {
        "prelaunch": prelaunch,
        "registration_enabled": True,
        "questionnaire_enabled": True,
        "photo_upload_enabled": True,
        "own_compatibility_profile_enabled": True,
        "waitlist_enabled": prelaunch,
        "candidate_output_enabled": matching,
        "interest_actions_enabled": matching,
    }
