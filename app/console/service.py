from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Conversation,
    Interest,
    MarketingAttribution,
    Match,
    Message,
    Photo,
    Profile,
    QuestionnaireQuestion,
    QuestionnaireVersion,
    Report,
    Setting,
    User,
)
from app.profile.service import user_age
from .access import ConsoleAccessDenied, require_console


CONSOLE_SECTIONS = (
    "Dashboard",
    "Users",
    "Profiles",
    "Photos",
    "Reports",
    "Matches",
    "Chats metadata",
    "Questionnaire",
    "Matching settings",
    "Marketing",
    "Analytics",
    "Audience balance",
)


def console_sections(db: Session, *, console_user_id: int) -> tuple[str, ...]:
    require_console(db, user_id=console_user_id, minimum_role="VIEWER")
    return CONSOLE_SECTIONS


def _age_band(age: int) -> str:
    if age <= 23:
        return "18–23"
    if age <= 28:
        return "24–28"
    if age <= 35:
        return "29–35"
    if age <= 45:
        return "36–45"
    return "46+"


def dashboard(db: Session, *, console_user_id: int) -> dict[str, Any]:
    require_console(db, user_id=console_user_id, minimum_role="VIEWER")

    profiles = list(db.execute(select(Profile)).scalars())
    user_status = {
        user_id: status
        for user_id, status in db.execute(select(User.id, User.status)).all()
    }
    completed = sum(1 for p in profiles if p.profile_completed)
    active_matchable = sum(
        1
        for p in profiles
        if user_status.get(p.user_id) == "ACTIVE"
        and p.profile_completed
        and p.questionnaire_completed
        and p.partner_preferences_completed
        and p.photos_completed
        and p.eligibility_status == "ACTIVE_FOR_MATCHING"
        and p.relationship_status in {"ACTIVE_SEARCH", "OPEN_TO_MATCH"}
    )

    pair_rows = db.execute(select(Match.user1, Match.user2)).all()
    users_with_match = len({uid for row in pair_rows for uid in row})
    interested = int(
        db.scalar(
            select(func.count()).select_from(Interest).where(Interest.state == "INTERESTED")
        )
        or 0
    )
    match_count = len(pair_rows)
    chats_started = int(
        db.scalar(
            select(func.count(func.distinct(Message.conversation_id))).select_from(Message)
        )
        or 0
    )

    gender_counts = Counter(p.gender or "UNKNOWN" for p in profiles)
    relationship_counts = Counter(p.relationship_status for p in profiles)
    city_counts = Counter((p.city or "Не указан").strip() or "Не указан" for p in profiles)
    age_counts: Counter[str] = Counter()
    for p in profiles:
        if p.dob is None:
            continue
        age = user_age(p.dob)
        if age >= 18:
            age_counts[_age_band(age)] += 1

    return {
        "metrics": {
            "ACTIVE_MATCHABLE_USERS": active_matchable,
            "COMPLETED_PROFILES": completed,
            "USERS_WITH_AT_LEAST_ONE_MATCH": users_with_match,
            "MATCH_RATE": round(users_with_match * 100 / max(1, completed), 1),
            "MUTUAL_INTEREST_RATE": round(match_count * 100 / max(1, interested), 1),
            "CONVERSATION_START_RATE": round(chats_started * 100 / max(1, match_count), 1),
            "TOTAL_REGISTRATIONS": len(user_status),
            "MEN": int(gender_counts.get("M", 0)),
            "WOMEN": int(gender_counts.get("F", 0)),
            "COMPLETED": completed,
            "INCOMPLETE": max(0, len(profiles) - completed),
            "ACTIVE_SEARCH": int(relationship_counts.get("ACTIVE_SEARCH", 0)),
            "OPEN_TO_MATCH": int(relationship_counts.get("OPEN_TO_MATCH", 0)),
            "PAUSED": int(relationship_counts.get("PAUSED", 0)),
            "IN_RELATIONSHIP": int(relationship_counts.get("IN_RELATIONSHIP", 0)),
        },
        "age_distribution": dict(age_counts),
        "cities": dict(city_counts),
        "photos_pending": int(
            db.scalar(
                select(func.count()).select_from(Photo).where(Photo.moderation_status == "PENDING")
            )
            or 0
        ),
        "reports_open": int(
            db.scalar(
                select(func.count())
                .select_from(Report)
                .where(Report.status.in_(("OPEN", "IN_REVIEW")))
            )
            or 0
        ),
    }


def list_users(
    db: Session,
    *,
    console_user_id: int,
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
) -> list[dict[str, Any]]:
    require_console(db, user_id=console_user_id, minimum_role="VIEWER")
    if limit < 1 or limit > 500 or offset < 0:
        raise ValueError("invalid_pagination")
    query = select(User)
    if status:
        query = query.where(User.status == status)
    rows = db.execute(
        query.order_by(User.id.desc()).offset(offset).limit(limit)
    ).scalars()
    return [
        {
            "id": u.id,
            "email": u.email,
            "status": u.status,
            "email_verified": u.email_verified_at is not None,
            "phone_verified": u.phone_verified_at is not None,
            "created_at": u.created_at,
        }
        for u in rows
    ]


def list_profiles(
    db: Session,
    *,
    console_user_id: int,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    require_console(db, user_id=console_user_id, minimum_role="VIEWER")
    rows = db.execute(
        select(Profile).order_by(Profile.user_id.desc()).offset(offset).limit(limit)
    ).scalars()
    return [
        {
            "user_id": p.user_id,
            "display_name": p.display_name,
            "gender": p.gender,
            "city": p.city,
            "relationship_status": p.relationship_status,
            "eligibility_status": p.eligibility_status,
            "profile_completed": p.profile_completed,
            "questionnaire_completed": p.questionnaire_completed,
            "partner_preferences_completed": p.partner_preferences_completed,
            "photos_completed": p.photos_completed,
            "updated_at": p.updated_at,
        }
        for p in rows
    ]


def list_photos(
    db: Session,
    *,
    console_user_id: int,
    moderation_status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    require_console(db, user_id=console_user_id, minimum_role="MODERATOR")
    query = select(Photo)
    if moderation_status:
        query = query.where(Photo.moderation_status == moderation_status)
    rows = db.execute(
        query.order_by(Photo.created_at, Photo.id).limit(limit)
    ).scalars()
    return [
        {
            "id": p.id,
            "user_id": p.user_id,
            "mime": p.mime,
            "byte_size": p.byte_size,
            "is_main": p.is_main,
            "sort_order": p.sort_order,
            "moderation_status": p.moderation_status,
            "moderation_reason": p.moderation_reason,
            "created_at": p.created_at,
        }
        for p in rows
    ]


def list_reports(
    db: Session,
    *,
    console_user_id: int,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    require_console(db, user_id=console_user_id, minimum_role="MODERATOR")
    query = select(Report)
    if status:
        query = query.where(Report.status == status)
    rows = db.execute(
        query.order_by(Report.created_at, Report.id).limit(limit)
    ).scalars()
    return [
        {
            "id": row.id,
            "reporter": row.reporter,
            "target_user": row.target_user,
            "photo_id": row.photo_id,
            "message_id": row.message_id,
            "reason": row.reason,
            "status": row.status,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def list_matches(
    db: Session,
    *,
    console_user_id: int,
    limit: int = 100,
) -> list[dict[str, Any]]:
    require_console(db, user_id=console_user_id, minimum_role="VIEWER")
    rows = db.execute(
        select(Match).order_by(Match.created_at.desc(), Match.id.desc()).limit(limit)
    ).scalars()
    return [
        {
            "id": m.id,
            "user1": m.user1,
            "user2": m.user2,
            "compatibility_score": m.compatibility_score,
            "mutual_fit_score": m.mutual_fit_score,
            "algorithm_version": m.algorithm_version,
            "created_at": m.created_at,
        }
        for m in rows
    ]


def chat_metadata(
    db: Session,
    *,
    console_user_id: int,
    limit: int = 100,
) -> list[dict[str, Any]]:
    require_console(db, user_id=console_user_id, minimum_role="MODERATOR")
    rows = db.execute(
        select(
            Conversation.id,
            Conversation.match_id,
            Conversation.created_at,
            func.count(Message.id).label("message_count"),
            func.max(Message.created_at).label("last_message_at"),
        )
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .group_by(Conversation.id)
        .order_by(Conversation.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "conversation_id": row.id,
            "match_id": row.match_id,
            "created_at": row.created_at,
            "message_count": int(row.message_count or 0),
            "last_message_at": row.last_message_at,
        }
        for row in rows
    ]


def questionnaire_overview(
    db: Session,
    *,
    console_user_id: int,
) -> list[dict[str, Any]]:
    require_console(db, user_id=console_user_id, minimum_role="VIEWER")
    rows = db.execute(
        select(
            QuestionnaireVersion.id,
            QuestionnaireVersion.code,
            QuestionnaireVersion.title,
            QuestionnaireVersion.is_active,
            func.count(QuestionnaireQuestion.id).label("question_count"),
        )
        .outerjoin(
            QuestionnaireQuestion,
            QuestionnaireQuestion.version_id == QuestionnaireVersion.id,
        )
        .group_by(QuestionnaireVersion.id)
        .order_by(QuestionnaireVersion.id.desc())
    ).all()
    return [
        {
            "id": row.id,
            "code": row.code,
            "title": row.title,
            "is_active": row.is_active,
            "question_count": int(row.question_count or 0),
        }
        for row in rows
    ]


def settings_overview(db: Session, *, console_user_id: int) -> dict[str, str]:
    require_console(db, user_id=console_user_id, minimum_role="ADMIN")
    rows = db.execute(select(Setting).order_by(Setting.key)).scalars()
    return {row.key: row.value for row in rows}


def marketing_overview(
    db: Session,
    *,
    console_user_id: int,
) -> list[dict[str, Any]]:
    require_console(db, user_id=console_user_id, minimum_role="VIEWER")
    rows = db.execute(
        select(
            MarketingAttribution.utm_source,
            func.count(MarketingAttribution.user_id).label("registrations"),
            func.sum(
                case(
                    (
                        Profile.profile_completed.is_(True),
                        1,
                    ),
                    else_=0,
                )
            ).label("completed_profiles"),
        )
        .outerjoin(Profile, Profile.user_id == MarketingAttribution.user_id)
        .group_by(MarketingAttribution.utm_source)
        .order_by(func.count(MarketingAttribution.user_id).desc())
    ).all()
    return [
        {
            "source": (row.utm_source or "direct").strip() or "direct",
            "registrations": int(row.registrations or 0),
            "completed_profiles": int(row.completed_profiles or 0),
        }
        for row in rows
    ]
