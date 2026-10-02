from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Market, Profile, User
from app.profile.service import user_age


AGE_BANDS = (
    ("18–23", 18, 23, 21),
    ("24–28", 24, 28, 26),
    ("29–35", 29, 35, 32),
    ("36–45", 36, 45, 40),
    ("46+", 46, 100, 50),
)
GENDERS = ("F", "M", "OTHER")


def age_band(age: int) -> str | None:
    if age < 18:
        return None
    for label, minimum, maximum, _ in AGE_BANDS:
        if minimum <= age <= maximum:
            return label
    return "46+"


def ready_profiles(db: Session, *, market_code: str | None = None) -> list[Profile]:
    query = (
        select(Profile)
        .join(User, User.id == Profile.user_id)
        .join(Market, Market.id == Profile.market_id)
        .where(
            User.status == "ACTIVE",
            Profile.profile_completed.is_(True),
            Profile.questionnaire_completed.is_(True),
            Profile.partner_preferences_completed.is_(True),
            Profile.photos_completed.is_(True),
            Profile.eligibility_status == "ACTIVE_FOR_MATCHING",
            Profile.relationship_status.in_(("ACTIVE_SEARCH", "OPEN_TO_MATCH")),
            Market.registration_open.is_(True),
        )
    )
    if market_code:
        query = query.where(Market.code == market_code)
    return list(db.execute(query).scalars())


def overview(db: Session, *, market_code: str | None = None) -> dict[str, Any]:
    query = select(Profile).join(User, User.id == Profile.user_id).where(User.status == "ACTIVE")
    if market_code:
        query = (
            query.join(Market, Market.id == Profile.market_id)
            .where(Market.code == market_code)
        )
    profiles = list(db.execute(query).scalars())
    ready = ready_profiles(db, market_code=market_code)

    genders = Counter(p.gender or "UNKNOWN" for p in ready)
    ages: Counter[str] = Counter()
    cities: Counter[str] = Counter()
    relationship = Counter(p.relationship_status for p in profiles)

    for profile in ready:
        cities[(profile.city or "Не указан").strip() or "Не указан"] += 1
        if profile.dob is not None:
            band = age_band(user_age(profile.dob))
            if band:
                ages[band] += 1

    completed = sum(1 for p in profiles if p.profile_completed)
    return {
        "market_code": market_code,
        "active_matchable_users": len(ready),
        "women": int(genders.get("F", 0)),
        "men": int(genders.get("M", 0)),
        "other_gender": int(genders.get("OTHER", 0)),
        "age_distribution": dict(ages),
        "cities": dict(cities),
        "completed_profiles": completed,
        "incomplete_profiles": max(0, len(profiles) - completed),
        "active_search": int(relationship.get("ACTIVE_SEARCH", 0)),
        "open_to_match": int(relationship.get("OPEN_TO_MATCH", 0)),
        "paused": int(relationship.get("PAUSED", 0)),
        "in_relationship": int(relationship.get("IN_RELATIONSHIP", 0)),
    }
