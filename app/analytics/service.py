from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Interest, Match, Message, ProductEvent, Profile, Report, User
from .events import (
    EVENT_CHAT_STARTED,
    EVENT_MUTUAL_MATCH,
    EVENT_PHOTO_UPLOADED,
    EVENT_PROFILE_COMPLETED,
    EVENT_QUESTIONNAIRE_COMPLETED,
    EVENT_QUESTIONNAIRE_STARTED,
    EVENT_REGISTRATION,
    EVENT_SUBSCRIPTION_STARTED,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _pct(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator * 100.0 / denominator, 1)


def _unique_event_users(db: Session, event_type: str) -> int:
    return int(
        db.scalar(
            select(func.count(func.distinct(ProductEvent.user_id))).where(
                ProductEvent.event_type == event_type,
                ProductEvent.user_id.is_not(None),
            )
        )
        or 0
    )


def users_with_relevant_match(db: Session) -> int:
    rows = db.execute(select(Match.user1, Match.user2)).all()
    return len({user_id for pair in rows for user_id in pair})


def _retention_rate(
    db: Session,
    *,
    day: int,
    now: datetime,
) -> float | None:
    if day < 1:
        raise ValueError("retention day must be >= 1")

    eligible_users = list(
        db.execute(
            select(User.id, User.created_at).where(
                User.created_at <= now - timedelta(days=day)
            )
        ).all()
    )
    if not eligible_users:
        return None

    retained = 0
    for user_id, registered_at in eligible_users:
        window_start = registered_at + timedelta(days=day)
        window_end = window_start + timedelta(days=1)
        active = db.execute(
            select(ProductEvent.id)
            .where(
                ProductEvent.user_id == user_id,
                ProductEvent.created_at >= window_start,
                ProductEvent.created_at < window_end,
                ProductEvent.event_type != EVENT_REGISTRATION,
            )
            .limit(1)
        ).first()
        if active is not None:
            retained += 1
    return _pct(retained, len(eligible_users))


def analytics_overview(
    db: Session,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or utcnow()
    registrations = int(db.scalar(select(func.count()).select_from(User)) or 0)

    questionnaire_started = _unique_event_users(db, EVENT_QUESTIONNAIRE_STARTED)
    questionnaire_completed = int(
        db.scalar(
            select(func.count()).select_from(Profile).where(
                Profile.questionnaire_completed.is_(True)
            )
        )
        or 0
    )
    profiles_completed = int(
        db.scalar(
            select(func.count()).select_from(Profile).where(
                Profile.profile_completed.is_(True)
            )
        )
        or 0
    )
    users_with_match = users_with_relevant_match(db)
    interests_sent = int(
        db.scalar(
            select(func.count()).select_from(Interest).where(
                Interest.state == "INTERESTED"
            )
        )
        or 0
    )
    mutual_matches = int(db.scalar(select(func.count()).select_from(Match)) or 0)
    chat_started_conversations = int(
        db.scalar(
            select(func.count(func.distinct(Message.conversation_id))).select_from(Message)
        )
        or 0
    )
    reports = int(db.scalar(select(func.count()).select_from(Report)) or 0)

    subscription_started = _unique_event_users(db, EVENT_SUBSCRIPTION_STARTED)
    subscription_available = subscription_started > 0

    return {
        "counts": {
            "registrations": registrations,
            "questionnaire_started": questionnaire_started,
            "questionnaire_completed": questionnaire_completed,
            "profiles_completed": profiles_completed,
            "users_with_relevant_match": users_with_match,
            "interests_sent": interests_sent,
            "mutual_matches": mutual_matches,
            "chat_started_conversations": chat_started_conversations,
            "reports": reports,
        },
        "metrics": {
            "registration_conversion": None,
            "questionnaire_start_rate": _pct(questionnaire_started, registrations),
            "questionnaire_completion_rate": _pct(
                questionnaire_completed,
                questionnaire_started,
            ),
            "profile_completion_rate": _pct(profiles_completed, registrations),
            "match_rate": _pct(users_with_match, profiles_completed),
            "mutual_interest_rate": _pct(mutual_matches, interests_sent),
            "chat_start_rate": _pct(chat_started_conversations, mutual_matches),
            "D1": _retention_rate(db, day=1, now=now),
            "D7": _retention_rate(db, day=7, now=now),
            "D30": _retention_rate(db, day=30, now=now),
            "subscription_conversion": (
                _pct(subscription_started, registrations)
                if subscription_available
                else None
            ),
            "report_rate": _pct(reports, registrations),
            "USERS_WITH_RELEVANT_MATCH": users_with_match,
        },
        "unavailable": {
            "registration_conversion": (
                "Нужен знаменатель визитов/установок. Phase 16 не подменяет его регистрациями."
            ),
            "subscription_conversion": (
                None
                if subscription_available
                else "Подписки появятся в Phase 18; до этого метрика не выдумывается."
            ),
        },
        "definitions": {
            "USERS_WITH_RELEVANT_MATCH": (
                "Уникальные пользователи, участвующие хотя бы в одном взаимном MatchLab match."
            ),
            "retention": (
                "D1/D7/D30: доля пользователей, достаточно давно зарегистрированных, "
                "у которых есть продуктовая активность в соответствующее 24-часовое окно."
            ),
        },
    }
