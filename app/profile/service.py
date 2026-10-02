from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Market, Profile, User, UserStatusHistory


RELATIONSHIP_STATUSES = {
    "ACTIVE_SEARCH",
    "OPEN_TO_MATCH",
    "PAUSED",
    "IN_RELATIONSHIP",
    "NOT_ACTIVE",
}
ELIGIBILITY_STATUSES = {
    "ACTIVE_FOR_MATCHING",
    "NOT_ACTIVE_FOR_MATCHING",
}
GENDERS = {"M", "F", "OTHER"}
SEEK_GENDERS = {"M", "F", "ANY", "OTHER"}


class ProfileError(Exception):
    pass


class UnderageUser(ProfileError):
    pass


class MarketUnavailable(ProfileError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def user_age(dob: date, today: date | None = None) -> int:
    today = today or date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def derive_status(in_relationship: bool, openness: str) -> tuple[str, str]:
    if in_relationship:
        return "IN_RELATIONSHIP", "NOT_ACTIVE_FOR_MATCHING"
    mapping = {
        "ACTIVE": ("ACTIVE_SEARCH", "ACTIVE_FOR_MATCHING"),
        "OPEN": ("OPEN_TO_MATCH", "ACTIVE_FOR_MATCHING"),
        "UNSURE": ("PAUSED", "NOT_ACTIVE_FOR_MATCHING"),
        "NO": ("NOT_ACTIVE", "NOT_ACTIVE_FOR_MATCHING"),
    }
    try:
        return mapping[openness]
    except KeyError as exc:
        raise ProfileError("Invalid openness value") from exc


def readiness_score(chat: str, offline: str) -> int:
    chat_points = {"YES": 60, "RATHER_YES": 42, "LOOK_ONLY": 12}.get(chat, 0)
    offline_points = {"YES": 40, "MAYBE": 24, "NO": 0}.get(offline, 0)
    return max(0, min(100, chat_points + offline_points))


def ensure_market(
    db: Session,
    *,
    code: str,
    country_code: str,
    city_code: str,
    display_name: str,
    timezone_name: str,
    currency_code: str,
    default_language: str,
    supported_languages: list[str],
    latitude: float | None = None,
    longitude: float | None = None,
    registration_open: bool = True,
    matching_open: bool = False,
) -> Market:
    market = db.execute(select(Market).where(Market.code == code)).scalar_one_or_none()
    if market is None:
        market = Market(
            code=code,
            country_code=country_code.upper(),
            city_code=city_code,
            display_name=display_name,
            timezone=timezone_name,
            currency_code=currency_code.upper(),
            default_language=default_language,
            latitude=latitude,
            longitude=longitude,
            supported_languages=supported_languages,
            registration_open=registration_open,
            matching_open=matching_open,
        )
        db.add(market)
        db.flush()
        return market

    market.country_code = country_code.upper()
    market.city_code = city_code
    market.display_name = display_name
    market.timezone = timezone_name
    market.currency_code = currency_code.upper()
    market.default_language = default_language
    market.latitude = latitude
    market.longitude = longitude
    market.supported_languages = supported_languages
    market.registration_open = registration_open
    market.matching_open = matching_open
    market.updated_at = utcnow()
    db.flush()
    return market


def _validate_basic(*, display_name: str, dob: date, gender: str, seek_gender: str, market: Market):
    if user_age(dob) < 18:
        raise UnderageUser("MatchLab is available only to users aged 18 or older")
    if not (display_name or "").strip():
        raise ProfileError("Display name is required")
    if gender not in GENDERS:
        raise ProfileError("Invalid gender")
    if seek_gender not in SEEK_GENDERS:
        raise ProfileError("Invalid seek gender")
    if not market.registration_open:
        raise MarketUnavailable("Registration is not available in this market")


def upsert_basic_profile(
    db: Session,
    *,
    user_id: int,
    display_name: str,
    dob: date,
    gender: str,
    seek_gender: str,
    market_code: str,
    preferred_locale: str | None = None,
    now: datetime | None = None,
) -> Profile:
    now = now or utcnow()
    user = db.get(User, user_id)
    if user is None:
        raise ProfileError("User not found")
    market = db.execute(select(Market).where(Market.code == market_code)).scalar_one_or_none()
    if market is None:
        raise MarketUnavailable("Unknown market")
    _validate_basic(
        display_name=display_name,
        dob=dob,
        gender=gender,
        seek_gender=seek_gender,
        market=market,
    )

    profile = db.get(Profile, user_id)
    if profile is None:
        profile = Profile(user_id=user_id)
        db.add(profile)

    profile.display_name = display_name.strip()
    profile.dob = dob
    profile.gender = gender
    profile.seek_gender = seek_gender
    profile.market_id = market.id
    profile.city = market.display_name
    profile.country_code = market.country_code
    profile.preferred_locale = preferred_locale or market.default_language
    profile.updated_at = now
    db.flush()
    return profile


def set_relationship_state(
    db: Session,
    *,
    user_id: int,
    in_relationship: bool,
    openness: str,
    source: str = "user",
    now: datetime | None = None,
) -> Profile:
    now = now or utcnow()
    profile = db.get(Profile, user_id)
    if profile is None:
        raise ProfileError("Profile not found")

    relationship_status, eligibility_status = derive_status(in_relationship, openness)
    profile.relationship_status = relationship_status
    profile.eligibility_status = eligibility_status
    profile.status_confirmed_at = now
    profile.updated_at = now
    db.add(
        UserStatusHistory(
            user_id=user_id,
            relationship_status=relationship_status,
            eligibility_status=eligibility_status,
            source=source,
            created_at=now,
        )
    )
    db.flush()
    return profile


def set_readiness(
    db: Session,
    *,
    user_id: int,
    chat: str,
    offline: str,
    now: datetime | None = None,
) -> Profile:
    now = now or utcnow()
    profile = db.get(Profile, user_id)
    if profile is None:
        raise ProfileError("Profile not found")
    profile.readiness_chat = chat
    profile.readiness_offline = offline
    profile.readiness_score = readiness_score(chat, offline)
    profile.updated_at = now
    db.flush()
    return profile


def confirm_status(
    db: Session,
    *,
    user_id: int,
    now: datetime | None = None,
) -> Profile:
    now = now or utcnow()
    profile = db.get(Profile, user_id)
    if profile is None:
        raise ProfileError("Profile not found")
    profile.status_confirmed_at = now
    profile.updated_at = now
    db.flush()
    return profile


def is_matchable(profile: Profile | None, market: Market | None, today: date | None = None) -> bool:
    if profile is None or market is None:
        return False
    if profile.dob is None or user_age(profile.dob, today=today) < 18:
        return False
    if not market.matching_open:
        return False
    if profile.relationship_status not in {"ACTIVE_SEARCH", "OPEN_TO_MATCH"}:
        return False
    if profile.eligibility_status != "ACTIVE_FOR_MATCHING":
        return False
    if not profile.profile_completed or not profile.questionnaire_completed:
        return False
    if not profile.partner_preferences_completed:
        return False
    return True
