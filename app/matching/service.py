from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Block,
    Interest,
    Market,
    Match,
    PartnerPreference,
    ProductEvent,
    Profile,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    QuestionnaireVersion,
    Session as DbSession,
    User,
)
from app.profile.service import is_matchable, user_age
from .config import ALGORITHM_VERSION, CATEGORY_SECTIONS, FINAL_WEIGHTS, SOFT_IMPORTANCE_WEIGHT


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except Exception:
        return None


def _market(db: Session, profile: Profile | None) -> Market | None:
    if profile is None or profile.market_id is None:
        return None
    return db.get(Market, profile.market_id)


def _gender_direction_ok(source: Profile, target: Profile) -> bool:
    return source.seek_gender == "ANY" or source.seek_gender == target.gender


def _blocked(db: Session, a: int, b: int) -> bool:
    return db.execute(
        select(Block.blocker).where(
            or_(
                (Block.blocker == a) & (Block.blocked == b),
                (Block.blocker == b) & (Block.blocked == a),
            )
        )
    ).first() is not None


def _haversine_km(a: Market, b: Market) -> float | None:
    if a.id == b.id:
        return 0.0
    lat1, lon1, lat2, lon2 = map(
        _number, (a.latitude, a.longitude, b.latitude, b.longitude)
    )
    if None in (lat1, lon1, lat2, lon2):
        return None
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    h = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return radius * 2 * math.asin(min(1.0, math.sqrt(h)))


def _list_values(pref: PartnerPreference) -> list[str]:
    raw = pref.values_json
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw]


def _criterion_match(
    key: str,
    pref: PartnerPreference,
    *,
    source_profile: Profile,
    source_market: Market,
    target_profile: Profile,
    target_market: Market,
) -> bool | None:
    if pref.importance == "IGNORE":
        return True

    if key == "age":
        if target_profile.dob is None:
            return None
        age = user_age(target_profile.dob)
        minimum, maximum = _number(pref.min_value), _number(pref.max_value)
        if minimum is None or maximum is None:
            return None
        return minimum <= age <= maximum

    if key == "height":
        if target_profile.height is None:
            return None
        minimum, maximum = _number(pref.min_value), _number(pref.max_value)
        if minimum is None or maximum is None:
            return None
        return minimum <= target_profile.height <= maximum

    if key == "distance_km":
        maximum = _number(pref.max_value)
        if maximum is None:
            return None
        distance = _haversine_km(source_market, target_market)
        if distance is None:
            return None
        return distance <= maximum

    if key == "gender":
        values = _list_values(pref)
        return target_profile.gender in values if values else None

    if key == "market":
        values = _list_values(pref)
        return target_market.code in values if values else None

    attribute_map = {
        "dating_goal": "dating_goal",
        "children_status": "children_status",
        "children_plans": "children_plans",
        "smoking": "smoking",
        "alcohol": "alcohol",
        "lifestyle": "lifestyle",
    }
    if key in attribute_map:
        target = str(getattr(target_profile, attribute_map[key], "") or "")
        if not target:
            return None
        values = _list_values(pref)
        if "ANY" in values:
            return True
        return target in values if values else None

    if key in {"religion", "nationality"}:
        target = str(getattr(target_profile, key, "") or "").strip()
        if not target:
            return None
        values = [x.casefold() for x in _list_values(pref)]
        return target.casefold() in values if values else None

    return None


def _preferences(db: Session, user_id: int) -> list[PartnerPreference]:
    return list(
        db.execute(
            select(PartnerPreference).where(PartnerPreference.user_id == user_id)
        ).scalars()
    )


def _hard_filter_direction(
    db: Session,
    source_profile: Profile,
    source_market: Market,
    target_profile: Profile,
    target_market: Market,
) -> tuple[bool, str | None]:
    for pref in _preferences(db, source_profile.user_id):
        if pref.importance != "HARD":
            continue
        result = _criterion_match(
            pref.criterion_key,
            pref,
            source_profile=source_profile,
            source_market=source_market,
            target_profile=target_profile,
            target_market=target_market,
        )
        if result is not True:
            return False, pref.criterion_key
    return True, None


def mutual_hard_pass(db: Session, user_a: int, user_b: int) -> tuple[bool, str | None]:
    if user_a == user_b:
        return False, "same_user"
    ua, ub = db.get(User, user_a), db.get(User, user_b)
    if ua is None or ua.status != "ACTIVE":
        return False, "source_user_inactive"
    if ub is None or ub.status != "ACTIVE":
        return False, "target_user_inactive"
    pa, pb = db.get(Profile, user_a), db.get(Profile, user_b)
    ma, mb = _market(db, pa), _market(db, pb)
    if not is_matchable(pa, ma):
        return False, "source_not_matchable"
    if not is_matchable(pb, mb):
        return False, "target_not_matchable"
    if _blocked(db, user_a, user_b):
        return False, "blocked"
    if not _gender_direction_ok(pa, pb):
        return False, "source_gender_direction"
    if not _gender_direction_ok(pb, pa):
        return False, "target_gender_direction"

    ok, key = _hard_filter_direction(db, pa, ma, pb, mb)
    if not ok:
        return False, f"source_hard:{key}"
    ok, key = _hard_filter_direction(db, pb, mb, pa, ma)
    if not ok:
        return False, f"target_hard:{key}"
    return True, None


def _active_questionnaire(db: Session) -> QuestionnaireVersion | None:
    versions = db.execute(
        select(QuestionnaireVersion).where(QuestionnaireVersion.is_active.is_(True))
    ).scalars().all()
    return versions[0] if len(versions) == 1 else None


def _answer_map(db: Session, user_id: int, version_id: int) -> dict[int, tuple[Any, QuestionnaireQuestion]]:
    rows = db.execute(
        select(QuestionnaireAnswer, QuestionnaireQuestion)
        .join(QuestionnaireQuestion, QuestionnaireQuestion.id == QuestionnaireAnswer.question_id)
        .where(
            QuestionnaireAnswer.user_id == user_id,
            QuestionnaireQuestion.version_id == version_id,
        )
    ).all()
    out = {}
    for answer, question in rows:
        value: Any
        if answer.value_int is not None:
            value = answer.value_int
        elif answer.value_json is not None:
            value = answer.value_json
        else:
            value = answer.value_text
        out[question.id] = (value, question)
    return out


def _question_similarity(a: Any, b: Any, question: QuestionnaireQuestion) -> float | None:
    kind = question.answer_type
    if kind == "scale":
        if not isinstance(a, int) or not isinstance(b, int):
            return None
        minimum = int((question.match_logic or {}).get("scale_min", 1))
        maximum = int((question.match_logic or {}).get("scale_max", 5))
        span = max(1, maximum - minimum)
        return max(0.0, 100.0 - (100.0 / span) * abs(a - b))

    if kind in {"single", "priority"}:
        if a is None or b is None:
            return None
        return 100.0 if str(a) == str(b) else 0.0

    if kind == "multiple":
        if not isinstance(a, list) or not isinstance(b, list):
            return None
        sa, sb = set(map(str, a)), set(map(str, b))
        if not sa and not sb:
            return 100.0
        union = sa | sb
        return 100.0 * len(sa & sb) / len(union) if union else None

    return None


def category_scores(db: Session, user_a: int, user_b: int) -> dict[str, int]:
    version = _active_questionnaire(db)
    if version is None:
        return {}
    aa, bb = _answer_map(db, user_a, version.id), _answer_map(db, user_b, version.id)
    section_to_category = {
        section: category
        for category, sections in CATEGORY_SECTIONS.items()
        for section in sections
    }
    totals = {key: [0.0, 0.0] for key in CATEGORY_SECTIONS}

    for qid, (a_value, question) in aa.items():
        if qid not in bb:
            continue
        category = section_to_category.get(question.category)
        if category is None:
            continue
        b_value, _ = bb[qid]
        similarity = _question_similarity(a_value, b_value, question)
        if similarity is None:
            continue
        weight = float(question.weight or 1)
        totals[category][0] += similarity * weight
        totals[category][1] += weight

    return {
        category: int(round(total / weight))
        for category, (total, weight) in totals.items()
        if weight > 0
    }


def compatibility_score(scores: dict[str, int]) -> int:
    if not scores:
        return 0
    return int(round(sum(scores.values()) / len(scores)))


def _soft_preference_direction(
    db: Session,
    source_profile: Profile,
    source_market: Market,
    target_profile: Profile,
    target_market: Market,
) -> int:
    earned = 0.0
    possible = 0.0
    for pref in _preferences(db, source_profile.user_id):
        weight = SOFT_IMPORTANCE_WEIGHT.get(pref.importance)
        if weight is None:
            continue
        result = _criterion_match(
            pref.criterion_key,
            pref,
            source_profile=source_profile,
            source_market=source_market,
            target_profile=target_profile,
            target_market=target_market,
        )
        if result is None:
            continue
        possible += weight
        if result:
            earned += weight
    if possible == 0:
        return 50
    return int(round(100 * earned / possible))


def mutual_preference_score(db: Session, user_a: int, user_b: int) -> int:
    pa, pb = db.get(Profile, user_a), db.get(Profile, user_b)
    ma, mb = _market(db, pa), _market(db, pb)
    if not pa or not pb or not ma or not mb:
        return 0
    ab = _soft_preference_direction(db, pa, ma, pb, mb)
    ba = _soft_preference_direction(db, pb, mb, pa, ma)
    return int(round((ab + ba) / 2))


def _last_activity(db: Session, profile: Profile) -> datetime | None:
    session_seen = db.scalar(
        select(func.max(DbSession.last_seen_at)).where(DbSession.user_id == profile.user_id)
    )
    event_seen = db.scalar(
        select(func.max(ProductEvent.created_at)).where(ProductEvent.user_id == profile.user_id)
    )
    values = [x for x in (session_seen, event_seen, profile.updated_at) if x is not None]
    return max(values) if values else None


def user_activity_score(db: Session, profile: Profile, *, now: datetime | None = None) -> int:
    now = now or utcnow()
    last = _last_activity(db, profile)
    if last is None:
        return 20
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    days = max(0.0, (now - last).total_seconds() / 86400)
    if days <= 1:
        return 100
    if days <= 3:
        return 90
    if days <= 7:
        return 75
    if days <= 14:
        return 55
    if days <= 30:
        return 35
    return 10


def evaluate_pair(
    db: Session,
    user_a: int,
    user_b: int,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    ok, reason = mutual_hard_pass(db, user_a, user_b)
    if not ok:
        return {
            "eligible": False,
            "reason": reason,
            "algorithm_version": ALGORITHM_VERSION,
        }

    pa, pb = db.get(Profile, user_a), db.get(Profile, user_b)
    ma, mb = _market(db, pa), _market(db, pb)
    scores = category_scores(db, user_a, user_b)
    comp = compatibility_score(scores)
    pref = mutual_preference_score(db, user_a, user_b)
    activity = int(round((
        user_activity_score(db, pa, now=now)
        + user_activity_score(db, pb, now=now)
    ) / 2))
    readiness = min(pa.readiness_score, pb.readiness_score)
    final = int(round(
        comp * FINAL_WEIGHTS["compatibility"]
        + pref * FINAL_WEIGHTS["mutual_preferences"]
        + activity * FINAL_WEIGHTS["activity"]
        + readiness * FINAL_WEIGHTS["readiness"]
    ))
    distance = _haversine_km(ma, mb)

    return {
        "eligible": True,
        "algorithm_version": ALGORITHM_VERSION,
        "category_scores": scores,
        "compatibility_score": comp,
        "mutual_preference_score": pref,
        "activity_score": activity,
        "readiness_score": readiness,
        "final_mutual_fit_score": max(0, min(100, final)),
        "distance_km": None if distance is None else round(distance, 1),
    }


def _excluded_candidate_ids(
    db: Session,
    *,
    user_id: int,
    now: datetime,
) -> set[int]:
    decision_ids = set(
        db.execute(
            select(Interest.to_user).where(
                Interest.from_user == user_id,
                or_(
                    Interest.state == "INTERESTED",
                    and_(
                        Interest.state == "SKIPPED",
                        or_(
                            Interest.snooze_until.is_(None),
                            Interest.snooze_until > now,
                        ),
                    ),
                ),
            )
        ).scalars()
    )

    matched_ids: set[int] = set()
    for user1, user2 in db.execute(
        select(Match.user1, Match.user2).where(
            or_(Match.user1 == user_id, Match.user2 == user_id)
        )
    ):
        matched_ids.add(user2 if user1 == user_id else user1)

    return decision_ids | matched_ids


def rank_candidates(
    db: Session,
    *,
    user_id: int,
    limit: int = 5,
    pool_limit: int = 5000,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    if limit < 1 or limit > 20:
        raise ValueError("limit must be between 1 and 20")
    now = now or utcnow()
    source = db.get(Profile, user_id)
    source_market = _market(db, source)
    if not is_matchable(source, source_market):
        return []

    excluded_ids = _excluded_candidate_ids(db, user_id=user_id, now=now)

    query = (
        select(Profile.user_id)
        .join(User, User.id == Profile.user_id)
        .join(Market, Market.id == Profile.market_id)
        .where(
            Profile.user_id != user_id,
            User.status == "ACTIVE",
            Profile.profile_completed.is_(True),
            Profile.questionnaire_completed.is_(True),
            Profile.partner_preferences_completed.is_(True),
            Profile.photos_completed.is_(True),
            Profile.eligibility_status == "ACTIVE_FOR_MATCHING",
            Profile.relationship_status.in_(("ACTIVE_SEARCH", "OPEN_TO_MATCH")),
            Market.matching_open.is_(True),
        )
    )
    if excluded_ids:
        query = query.where(Profile.user_id.not_in(excluded_ids))

    candidate_ids = list(
        db.execute(query.limit(pool_limit)).scalars()
    )

    ranked = []
    for candidate_id in candidate_ids:
        result = evaluate_pair(db, user_id, candidate_id, now=now)
        if not result["eligible"]:
            continue
        ranked.append({"user_id": candidate_id, **result})

    ranked.sort(
        key=lambda item: (
            -item["final_mutual_fit_score"],
            -item["compatibility_score"],
            item["user_id"],
        )
    )
    return ranked[:limit]
