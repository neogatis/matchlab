from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .service import (
    CONSOLE_SECTIONS,
    chat_metadata,
    dashboard,
    list_matches,
    list_photos,
    list_profiles,
    list_reports,
    list_users,
    marketing_overview,
    questionnaire_overview,
    settings_overview,
)


def load_section(
    db: Session,
    *,
    console_user_id: int,
    section: str,
    limit: int = 100,
) -> Any:
    if section not in CONSOLE_SECTIONS:
        raise ValueError("unknown_console_section")

    if section == "Dashboard":
        return dashboard(db, console_user_id=console_user_id)
    if section == "Users":
        return list_users(db, console_user_id=console_user_id, limit=limit)
    if section == "Profiles":
        return list_profiles(db, console_user_id=console_user_id, limit=limit)
    if section == "Photos":
        return list_photos(db, console_user_id=console_user_id, limit=limit)
    if section == "Reports":
        return list_reports(db, console_user_id=console_user_id, limit=limit)
    if section == "Matches":
        return list_matches(db, console_user_id=console_user_id, limit=limit)
    if section == "Chats metadata":
        return chat_metadata(db, console_user_id=console_user_id, limit=limit)
    if section == "Questionnaire":
        return questionnaire_overview(db, console_user_id=console_user_id)
    if section == "Matching settings":
        return settings_overview(db, console_user_id=console_user_id)
    if section == "Marketing":
        return marketing_overview(db, console_user_id=console_user_id)
    if section == "Analytics":
        data = dashboard(db, console_user_id=console_user_id)
        return {
            "metrics": data["metrics"],
            "photos_pending": data["photos_pending"],
            "reports_open": data["reports_open"],
        }
    if section == "Audience balance":
        data = dashboard(db, console_user_id=console_user_id)
        return {
            "age_distribution": data["age_distribution"],
            "cities": data["cities"],
            "metrics": {
                "MEN": data["metrics"]["MEN"],
                "WOMEN": data["metrics"]["WOMEN"],
                "ACTIVE_SEARCH": data["metrics"]["ACTIVE_SEARCH"],
                "OPEN_TO_MATCH": data["metrics"]["OPEN_TO_MATCH"],
                "PAUSED": data["metrics"]["PAUSED"],
                "IN_RELATIONSHIP": data["metrics"]["IN_RELATIONSHIP"],
            },
        }
    raise ValueError("unknown_console_section")
