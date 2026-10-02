from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PartnerPreference, Profile
from app.profile.service import user_age
from .core import AGE_BANDS, GENDERS, age_band, ready_profiles


def _preference_map(
    db: Session,
    user_ids: list[int],
) -> dict[int, dict[str, PartnerPreference]]:
    if not user_ids:
        return {}
    rows = db.execute(
        select(PartnerPreference).where(PartnerPreference.user_id.in_(user_ids))
    ).scalars()
    result: dict[int, dict[str, PartnerPreference]] = defaultdict(dict)
    for row in rows:
        result[row.user_id][row.criterion_key] = row
    return result


def _target_genders(
    profile: Profile,
    prefs: dict[str, PartnerPreference],
) -> set[str]:
    pref = prefs.get("gender")
    if pref is not None:
        if pref.importance == "IGNORE":
            return set(GENDERS)
        if isinstance(pref.values_json, list):
            values = {str(v) for v in pref.values_json if str(v) in GENDERS}
            if values:
                return values

    if profile.seek_gender == "ANY":
        return set(GENDERS)
    if profile.seek_gender in GENDERS:
        return {profile.seek_gender}
    return set(GENDERS)


def _age_range(
    prefs: dict[str, PartnerPreference],
) -> tuple[int, int]:
    pref = prefs.get("age")
    if pref is None or pref.importance == "IGNORE":
        return 18, 100
    minimum = int(pref.min_value) if pref.min_value is not None else 18
    maximum = int(pref.max_value) if pref.max_value is not None else 100
    return max(18, minimum), min(100, maximum)


def supply_demand_matrix(
    db: Session,
    *,
    market_code: str | None = None,
) -> list[dict[str, Any]]:
    ready = ready_profiles(db, market_code=market_code)
    pref_map = _preference_map(db, [p.user_id for p in ready])

    supply: Counter[tuple[str, str]] = Counter()
    for profile in ready:
        if profile.dob is None:
            continue
        band = age_band(user_age(profile.dob))
        if band:
            supply[(profile.gender, band)] += 1

    demand: Counter[tuple[str, str, str]] = Counter()
    for seeker in ready:
        prefs = pref_map.get(seeker.user_id, {})
        target_genders = _target_genders(seeker, prefs)
        minimum_age, maximum_age = _age_range(prefs)
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
        row
        for row in supply_demand_matrix(db, market_code=market_code)
        if row["gap"] > 0
    ]
    return [
        {
            **row,
            "priority": "HIGH" if row["gap"] >= 5 else "MEDIUM",
            "message": (
                f"Дефицит группы {row['target_gender']} {row['age_band']}: "
                f"спрос {row['demand']}, предложение {row['supply']}, "
                f"не хватает {row['gap']}."
            ),
        }
        for row in rows[:limit]
    ]
