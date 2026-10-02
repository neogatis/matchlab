from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Market,
    MarketingAttribution,
    PartnerPreference,
    Profile,
    User,
)
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


def _ready_profiles(db: Session, *, market_code: str | None = None) -> list[Profile]:
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


def _preference_map(db: Session, user_ids: list[int]) -> dict[int, dict[str, PartnerPreference]]:
    if not user_ids:
        return {}
    rows = db.execute(
        select(PartnerPreference).where(PartnerPreference.user_id.in_(user_ids))
    ).scalars()
    out: dict[int, dict[str, PartnerPreference]] = defaultdict(dict)
    for row in rows:
        out[row.user_id][row.criterion_key] = row
    return out


def _target_genders(profile: Profile, prefs: dict[str, PartnerPreference]) -> set[str]:
    pref = prefs.get("gender")
    if pref is not None:
        if pref.importance == "IGNORE":
            return set(GENDERS)
        if isinstance(pref.values_json, list):
            values = {str(value) for value in pref.values_json if str(value) in GENDERS}
            if values:
                return values
    if profile.seek_gender == "ANY":
        return set(GENDERS)
    if profile.seek_gender in GENDERS:
        return {profile.seek_gender}
    return set(GENDERS)


def _age_range(prefs: dict[str, PartnerPreference]) -> tuple[int, int]:
    pref = prefs.get("age")
    if pref is None or pref.importance == "IGNORE":
        return 18, 100
    minimum = int(pref.min_value) if pref.min_value is not None else 18
    maximum = int(pref.max_value) if pref.max_value is not None else 100
    return max(18, minimum), min(100, maximum)


def audience_overview(
    db: Session,
    *,
    market_code: str | None = None,
) -> dict[str, Any]:
    all_profiles_query = select(Profile).join(User, User.id == Profile.user_id).where(
        User.status == "ACTIVE"
    )
    if market_code:
        all_profiles_query = (
            all_profiles_query
            .join(Market, Market.id == Profile.market_id)
            .where(Market.code == market_code)
        )
    all_profiles = list(db.execute(all_profiles_query).scalars())
    ready = _ready_profiles(db, market_code=market_code)

    genders = Counter(p.gender or "UNKNOWN" for p in ready)
    ages: Counter[str] = Counter()
    cities: Counter[str] = Counter()
    relationship = Counter(p.relationship_status for p in all_profiles)

    for profile in ready:
        cities[(profile.city or "Не указан").strip() or "Не указан"] += 1
        if profile.dob is not None:
            band = age_band(user_age(profile.dob))
            if band:
                ages[band] += 1

    completed = sum(1 for p in all_profiles if p.profile_completed)
    return {
        "market_code": market_code,
        "active_matchable_users": len(ready),
        "women": int(genders.get("F", 0)),
        "men": int(genders.get("M", 0)),
        "other_gender": int(genders.get("OTHER", 0)),
        "age_distribution": dict(ages),
        "cities": dict(cities),
        "completed_profiles": completed,
        "incomplete_profiles": max(0, len(all_profiles) - completed),
        "active_search": int(relationship.get("ACTIVE_SEARCH", 0)),
        "open_to_match": int(relationship.get("OPEN_TO_MATCH", 0)),
        "paused": int(relationship.get("PAUSED", 0)),
        "in_relationship": int(relationship.get("IN_RELATIONSHIP", 0)),
    }


def supply_demand_matrix(
    db: Session,
    *,
    market_code: str | None = None,
) -> list[dict[str, Any]]:
    ready = _ready_profiles(db, market_code=market_code)
    prefs = _preference_map(db, [profile.user_id for profile in ready])

    supply: Counter[tuple[str, str]] = Counter()
    for profile in ready:
        if profile.dob is None:
            continue
        band = age_band(user_age(profile.dob))
        if band:
            supply[(profile.gender, band)] += 1

    demand: Counter[tuple[str, str, str]] = Counter()
    for seeker in ready:
        seeker_prefs = prefs.get(seeker.user_id, {})
        target_genders = _target_genders(seeker, seeker_prefs)
        minimum_age, maximum_age = _age_range(seeker_prefs)
        for target_gender in target_genders:
            for band_label, _, _, midpoint in AGE_BANDS:
                if minimum_age <= midpoint <= maximum_age:
                    demand[(seeker.gender, target_gender, band_label)] += 1

    rows: list[dict[str, Any]] = []
    for seeker_gender in GENDERS:
        for target_gender in GENDERS:
            for band_label, _, _, _ in AGE_BANDS:
                wanted = int(demand.get((seeker_gender, target_gender, band_label), 0))
                available = int(supply.get((target_gender, band_label), 0))
                if wanted == 0 and available == 0:
                    continue
                gap = max(0, wanted - available)
                rows.append(
                    {
                        "seeker_gender": seeker_gender,
                        "target_gender": target_gender,
                        "age_band": band_label,
                        "demand": wanted,
                        "supply": available,
                        "gap": gap,
                        "coverage_percent": round(
                            min(100.0, available * 100 / max(1, wanted)),
                            1,
                        ),
                    }
                )

    rows.sort(
        key=lambda row: (
            -row["gap"],
            -row["demand"],
            row["target_gender"],
            row["age_band"],
            row["seeker_gender"],
        )
    )
    return rows


def deficit_insights(
    db: Session,
    *,
    market_code: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if limit < 1 or limit > 20:
        raise ValueError("limit must be between 1 and 20")
    rows = [
        row for row in supply_demand_matrix(db, market_code=market_code)
        if row["gap"] > 0
    ]
    return [
        {
            **row,
            "priority": "HIGH" if row["gap"] >= 5 else "MEDIUM",
            "message": (
                f"Не хватает аудитории: {row['target_gender']} {row['age_band']} "
                f"— спрос {row['demand']}, доступно {row['supply']}, дефицит {row['gap']}."
            ),
        }
        for row in rows[:limit]
    ]


def source_breakdown(
    db: Session,
    *,
    market_code: str | None = None,
) -> list[dict[str, Any]]:
    ready_ids = {p.user_id for p in _ready_profiles(db, market_code=market_code)}
    users_query = select(User)
    if market_code:
        users_query = (
            users_query
            .join(Profile, Profile.user_id == User.id)
            .join(Market, Market.id == Profile.market_id)
            .where(Market.code == market_code)
        )
    users = list(db.execute(users_query).scalars())

    attributions = {
        row.user_id: row
        for row in db.execute(select(MarketingAttribution)).scalars()
    }
    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"registrations": 0, "completed_active": 0}
    )
    for user in users:
        attribution = attributions.get(user.id)
        if user.referred_by is not None:
            source = "referral"
        elif attribution is not None and (attribution.utm_source or "").strip():
            source = attribution.utm_source.strip()
        else:
            source = "direct"
        counts[source]["registrations"] += 1
        if user.id in ready_ids:
            counts[source]["completed_active"] += 1

    result = [
        {
            "source": source,
            "registrations": values["registrations"],
            "completed_active": values["completed_active"],
            "activation_rate": round(
                values["completed_active"] * 100 / max(1, values["registrations"]),
                1,
            ),
        }
        for source, values in counts.items()
    ]
    result.sort(key=lambda row: (-row["registrations"], row["source"]))
    return result


def audience_balance(
    db: Session,
    *,
    market_code: str | None = None,
) -> dict[str, Any]:
    matrix = supply_demand_matrix(db, market_code=market_code)
    return {
        "overview": audience_overview(db, market_code=market_code),
        "supply_demand": matrix,
        "total_demand_gap": sum(row["gap"] for row in matrix),
        "insights": deficit_insights(db, market_code=market_code),
        "sources": source_breakdown(db, market_code=market_code),
    }
