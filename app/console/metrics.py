from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Market, Photo, Profile, User
from app.profile.service import utcnow


def prelaunch_metrics(db: Session) -> dict[str, Any]:
    now = utcnow()

    def count_users(*where) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(User)
                .where(*where)
            )
            or 0
        )

    def count_profiles(*where) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(Profile)
                .where(*where)
            )
            or 0
        )

    active_users = count_users(User.status == "ACTIVE")
    profiles_started = count_profiles()

    basic_complete = count_profiles(
        Profile.display_name != "",
        Profile.dob.is_not(None),
        Profile.gender.in_(("M", "F", "OTHER")),
        Profile.seek_gender.in_(("M", "F", "ANY", "OTHER")),
        Profile.market_id.is_not(None),
    )

    details_complete = count_profiles(
        Profile.height.is_not(None),
        Profile.dating_goal.in_(("SERIOUS", "FAMILY", "SEE", "CHAT", "UNKNOWN")),
        Profile.children_status.in_(("NO_CHILDREN", "HAS_CHILDREN")),
        Profile.children_plans.in_(("WANTS", "MAYBE", "DOES_NOT_WANT")),
        Profile.smoking.in_(("NO", "RARE", "YES")),
        Profile.alcohol.in_(("NO", "RARE", "MODERATE", "YES")),
        Profile.lifestyle.in_(("CALM", "BALANCED", "ACTIVE", "VERY_ACTIVE")),
    )

    readiness_complete = count_profiles(
        Profile.readiness_chat.in_(("YES", "RATHER_YES", "LOOK_ONLY")),
        Profile.readiness_offline.in_(("YES", "MAYBE", "NO")),
    )

    questionnaire_complete = count_profiles(Profile.questionnaire_completed.is_(True))
    preferences_complete = count_profiles(Profile.partner_preferences_completed.is_(True))
    photos_complete = count_profiles(Profile.photos_completed.is_(True))
    profile_complete = count_profiles(Profile.profile_completed.is_(True))

    active_for_matching = int(
        db.scalar(
            select(func.count())
            .select_from(Profile)
            .join(User, User.id == Profile.user_id)
            .where(
                User.status == "ACTIVE",
                Profile.profile_completed.is_(True),
                Profile.eligibility_status == "ACTIVE_FOR_MATCHING",
                Profile.relationship_status.in_(("ACTIVE_SEARCH", "OPEN_TO_MATCH")),
            )
        )
        or 0
    )

    pending_photos = int(
        db.scalar(
            select(func.count())
            .select_from(Photo)
            .where(Photo.moderation_status == "PENDING")
        )
        or 0
    )

    gender_rows = db.execute(
        select(Profile.gender, func.count())
        .where(Profile.gender.in_(("M", "F", "OTHER")))
        .group_by(Profile.gender)
        .order_by(Profile.gender)
    ).all()

    market_rows = db.execute(
        select(Market.code, Market.display_name, func.count(Profile.user_id))
        .outerjoin(Profile, Profile.market_id == Market.id)
        .group_by(Market.id, Market.code, Market.display_name)
        .order_by(Market.code)
    ).all()

    relationship_rows = db.execute(
        select(Profile.relationship_status, func.count())
        .group_by(Profile.relationship_status)
        .order_by(Profile.relationship_status)
    ).all()

    funnel = [
        {"key": "registered", "label": "Активные регистрации", "count": active_users},
        {"key": "profile_started", "label": "Начали профиль", "count": profiles_started},
        {"key": "basic", "label": "Базовый профиль", "count": basic_complete},
        {"key": "details", "label": "Данные для подбора", "count": details_complete},
        {"key": "readiness", "label": "Готовность", "count": readiness_complete},
        {"key": "questionnaire", "label": "64 вопроса", "count": questionnaire_complete},
        {"key": "preferences", "label": "Критерии партнёра", "count": preferences_complete},
        {"key": "photos", "label": "Фото одобрены", "count": photos_complete},
        {"key": "profile_complete", "label": "Профиль завершён", "count": profile_complete},
        {"key": "waitlist_ready", "label": "Готовы к подбору", "count": active_for_matching},
    ]

    return {
        "generated_at": now,
        "users": {
            "active": active_users,
            "new_24h": count_users(
                User.status == "ACTIVE",
                User.created_at >= now - timedelta(hours=24),
            ),
            "new_7d": count_users(
                User.status == "ACTIVE",
                User.created_at >= now - timedelta(days=7),
            ),
        },
        "funnel": funnel,
        "pending_photos": pending_photos,
        "gender": {str(key): int(value) for key, value in gender_rows},
        "relationship": {str(key): int(value) for key, value in relationship_rows},
        "markets": [
            {
                "code": code,
                "name": name,
                "profiles": int(value),
            }
            for code, name, value in market_rows
        ],
    }
