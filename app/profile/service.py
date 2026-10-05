from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.events import EVENT_PROFILE_COMPLETED, EVENT_PROFILE_READY, track_once
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
DATING_GOALS = {"SERIOUS", "FAMILY", "SEE", "CHAT", "UNKNOWN"}
CHILDREN_STATUSES = {"NO_CHILDREN", "HAS_CHILDREN"}
CHILDREN_PLANS = {"WANTS", "MAYBE", "DOES_NOT_WANT"}
SMOKING_VALUES = {"NO", "RARE", "YES"}
ALCOHOL_VALUES = {"NO", "RARE", "MODERATE", "YES"}
LIFESTYLE_VALUES = {"CALM", "BALANCED", "ACTIVE", "VERY_ACTIVE"}
READINESS_CHAT_VALUES = {"YES", "RATHER_YES", "LOOK_ONLY"}
READINESS_OFFLINE_VALUES = {"YES", "MAYBE", "NO"}


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
    if chat not in READINESS_CHAT_VALUES:
        raise ProfileError("Invalid chat readiness value")
    if offline not in READINESS_OFFLINE_VALUES:
        raise ProfileError("Invalid offline readiness value")
    chat_points = {"YES": 60, "RATHER_YES": 42, "LOOK_ONLY": 12}[chat]
    offline_points = {"YES": 40, "MAYBE": 24, "NO": 0}[offline]
    return max(0, min(100, chat_points + offline_points))



def profile_details_complete(profile: Profile | None) -> bool:
    if profile is None:
        return False
    return bool(
        profile.height is not None
        and 100 <= int(profile.height) <= 250
        and profile.dating_goal in DATING_GOALS
        and profile.children_status in CHILDREN_STATUSES
        and profile.children_plans in CHILDREN_PLANS
        and profile.smoking in SMOKING_VALUES
        and profile.alcohol in ALCOHOL_VALUES
        and profile.lifestyle in LIFESTYLE_VALUES
    )


def readiness_complete(profile: Profile | None) -> bool:
    if profile is None:
        return False
    return bool(
        profile.readiness_chat in READINESS_CHAT_VALUES
        and profile.readiness_offline in READINESS_OFFLINE_VALUES
    )


def basic_profile_complete(profile: Profile | None) -> bool:
    if profile is None:
        return False
    return bool(
        (profile.display_name or "").strip()
        and profile.dob is not None
        and profile.gender in GENDERS
        and profile.seek_gender in SEEK_GENDERS
        and profile.market_id is not None
    )


def set_match_profile_details(
    db: Session,
    *,
    user_id: int,
    height: int,
    dating_goal: str,
    children_status: str,
    children_plans: str,
    smoking: str,
    alcohol: str,
    lifestyle: str,
    bio: str = "",
    religion: str = "",
    nationality: str = "",
    now: datetime | None = None,
) -> Profile:
    now = now or utcnow()
    profile = db.get(Profile, user_id)
    if profile is None:
        raise ProfileError("Profile not found")

    if isinstance(height, bool) or not isinstance(height, int) or not 100 <= height <= 250:
        raise ProfileError("Height must be between 100 and 250")
    if dating_goal not in DATING_GOALS:
        raise ProfileError("Invalid dating goal")
    if children_status not in CHILDREN_STATUSES:
        raise ProfileError("Invalid children status")
    if children_plans not in CHILDREN_PLANS:
        raise ProfileError("Invalid children plans")
    if smoking not in SMOKING_VALUES:
        raise ProfileError("Invalid smoking value")
    if alcohol not in ALCOHOL_VALUES:
        raise ProfileError("Invalid alcohol value")
    if lifestyle not in LIFESTYLE_VALUES:
        raise ProfileError("Invalid lifestyle value")

    bio = (bio or "").strip()
    religion = (religion or "").strip()
    nationality = (nationality or "").strip()
    if len(bio) > 2000:
        raise ProfileError("Bio is too long")
    if len(religion) > 120:
        raise ProfileError("Religion is too long")
    if len(nationality) > 120:
        raise ProfileError("Nationality is too long")

    profile.height = height
    profile.dating_goal = dating_goal
    profile.children_status = children_status
    profile.children_plans = children_plans
    profile.smoking = smoking
    profile.alcohol = alcohol
    profile.lifestyle = lifestyle
    profile.bio = bio
    profile.religion = religion
    profile.nationality = nationality
    profile.updated_at = now
    db.flush()
    recompute_profile_completion(db, user_id=user_id, now=now)
    return profile


def profile_completion_state(profile: Profile | None) -> dict[str, bool]:
    if profile is None:
        return {
            "basic": False,
            "details": False,
            "relationship": False,
            "readiness": False,
            "questionnaire": False,
            "partner_preferences": False,
            "photos": False,
            "profile": False,
        }
    relationship = bool(
        profile.status_confirmed_at is not None
        and profile.relationship_status in RELATIONSHIP_STATUSES
        and profile.eligibility_status in ELIGIBILITY_STATUSES
    )
    return {
        "basic": basic_profile_complete(profile),
        "details": profile_details_complete(profile),
        "relationship": relationship,
        "readiness": readiness_complete(profile),
        "questionnaire": bool(profile.questionnaire_completed),
        "partner_preferences": bool(profile.partner_preferences_completed),
        "photos": bool(profile.photos_completed),
        "profile": bool(profile.profile_completed),
    }


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
    city_name: str | None = None,
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
    city_name = (city_name or "").strip()
    if market.code == "KZ-OTHER":
        if not city_name:
            raise ProfileError("City is required")
        if len(city_name) > 120:
            raise ProfileError("City is too long")
        profile.city = city_name
    else:
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



def recompute_profile_completion(
    db: Session,
    *,
    user_id: int,
    now: datetime | None = None,
) -> bool:
    now = now or utcnow()
    profile = db.get(Profile, user_id)
    if profile is None:
        raise ProfileError("Profile not found")

    complete = bool(
        basic_profile_complete(profile)
        and profile_details_complete(profile)
        and readiness_complete(profile)
        and profile.questionnaire_completed
        and profile.partner_preferences_completed
        and profile.photos_completed
    )
    profile.profile_completed = complete
    profile.updated_at = now
    if complete:
        metadata = {"completion_model": "profile-v1"}
        track_once(
            db,
            event_type=EVENT_PROFILE_COMPLETED,
            user_id=user_id,
            metadata=metadata,
            now=now,
        )
        track_once(
            db,
            event_type=EVENT_PROFILE_READY,
            user_id=user_id,
            metadata=metadata,
            now=now,
        )
    db.flush()
    return complete


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
    if not profile.photos_completed:
        return False
    return True
